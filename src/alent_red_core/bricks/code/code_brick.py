import asyncio
import hashlib
import json
import os
import platform
import shutil
import signal
import ssl
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import certifi

from ..base_brick import BaseBrick
from ...common import Logger
from ...models import (
    BrickConfigCode,
    Conversation,
    Error,
    ErrorCode,
    MessageContentToolResponse,
    Tool,
)
from ...database import Database
from ...blob import BlobStorage

if TYPE_CHECKING:
    from ..brick_manager import BrickManager
    from ...looper import Looper
    from ...providers import ProviderManager


class CodeBrick(BaseBrick):
    """Code brick providing an isolated Python environment to the LLM."""

    _identifier = "code"

    _os_darwin = "Darwin"
    _os_windows = "Windows"

    _arch_arm64 = "arm64"
    _arch_x86_64 = "x86_64"

    _uv_version = "0.5.4"
    _uv_release_base_url = "https://github.com/astral-sh/uv/releases/download"

    _uv_macos_arm64_asset = "uv-aarch64-apple-darwin.tar.gz"
    _uv_macos_arm64_sha256 = "f924d82255a0b25fd04a78c7012f90300cdadfb72ca0af4508f3eeaf9509010f"
    _uv_macos_arm64_directory = "uv-aarch64-apple-darwin"

    _uv_macos_x86_64_asset = "uv-x86_64-apple-darwin.tar.gz"
    _uv_macos_x86_64_sha256 = "f879864954b2229611155bb201088d0f09becf1436b0ec8707c8f560e98e9209"
    _uv_macos_x86_64_directory = "uv-x86_64-apple-darwin"

    _uv_windows_x86_64_asset = "uv-x86_64-pc-windows-msvc.zip"
    _uv_windows_x86_64_sha256 = "db68a1850f156c89b82ecec359d09ba298fb1ce2a35dabc5072de458b175d8fb"

    _macos_brick_folder = (
        Path.home() / "Library" / "Application Support" / "AlentRed" / "code-brick"
    )
    _windows_brick_folder = Path(os.environ.get("LOCALAPPDATA", "")) / "AlentRed" / "code-brick"

    _venv_subfolder = "env"
    _uv_subfolder = "uv"
    _uv_repair_suffix = ".repair"
    _tooling_timeout_seconds = 60
    _uv_macos_binary_name = "uv"
    _uv_windows_binary_name = "uv.exe"

    _prompt_template = "Python environment {{VERSION}}, installed packages:\n{{PACKAGES}}"
    _prompt_no_packages = "No installed packages."
    _packages_separator = "\n"
    _package_prefix = "- "

    _tool_run_python_code = "run_python_code"
    _tool_install_python_packages = "install_python_packages"

    _output_max_bytes = 50_000
    _output_truncated_marker = "\n... [output truncated]"
    _output_encoding = "utf-8"
    _output_encoding_errors = "replace"

    _download_chunk_size = 65_536

    def __init__(
        self,
        config: BrickConfigCode,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize code brick.

        Args:
            config: Code brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        super().__init__(config, looper, bricks, providers, database, blob)
        self._logger = Logger.get_logger("bricks.code.code_brick")
        self._setup_error: Error | None = None
        self._brick_folder: Path | None = None
        self._uv_binary_path: Path | None = None
        self._venv_path: Path | None = None
        self._venv_python_path: Path | None = None

    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        return self._identifier

    async def setup(self) -> None:
        """Prepare the brick folder, uv binary and venv.

        Captures any failure into self._setup_error so the rest of the
        system stays online; downstream methods raise when the brick is
        not ready.
        """
        self._logger.info("setup_started")
        try:
            await asyncio.to_thread(self._setup_synchronously)
            self._setup_error = None
            self._logger.info(
                "setup_completed",
                brick_folder=str(self._brick_folder),
                venv_path=str(self._venv_path),
            )
        except Error as error:
            self._setup_error = error
            self._logger.warning("setup_failed", error_code=error.code.value, error=str(error))
        except Exception as exception:
            self._setup_error = Error(ErrorCode.INTERNAL, f"Unexpected setup failure: {exception}")
            self._logger.warning(
                "setup_failed", error_code=ErrorCode.INTERNAL.value, error=str(exception)
            )

    async def get_prompt(self, conversation: Conversation) -> str | None:
        """Build a prompt describing the Python environment.

        Args:
            conversation: Conversation object.

        Returns:
            Rendered prompt with Python version and installed packages.

        Raises:
            Error: If the brick is not ready.
        """
        self._ensure_ready()
        self._logger.debug("get_prompt_started", conversation_id=str(conversation.id))

        python_version = await self._read_python_version()
        installed_packages = await self._read_installed_packages()

        if not installed_packages:
            packages_block = self._prompt_no_packages
        else:
            packages_block = self._packages_separator.join(
                f"{self._package_prefix}{name}=={version}" for name, version in installed_packages
            )

        prompt = self._prompt_template.replace("{{VERSION}}", python_version).replace(
            "{{PACKAGES}}", packages_block
        )

        self._logger.debug(
            "get_prompt_completed",
            conversation_id=str(conversation.id),
            python_version=python_version,
            package_count=len(installed_packages),
        )

        return prompt

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick.

        Args:
            conversation: Conversation object.

        Returns:
            List of tools.

        Raises:
            Error: If the brick is not ready.
        """
        self._logger.debug("get_tools_started", conversation_id=str(conversation.id))
        self._ensure_ready()

        tools = [
            Tool(
                name=self._tool_run_python_code,
                description=(
                    "Run Python code in an isolated environment and return its exit code, "
                    "stdout and stderr. Code is written to a temporary file and executed; "
                    "tracebacks reference that file. Each call uses a fresh Python process "
                    "(no in-memory state carries over) but installed packages persist "
                    "across calls. Output is captured separately and truncated past 50000 "
                    "bytes per stream. Exceeding timeout_seconds kills the process tree "
                    "and returns timed_out=true with any captured output."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python source code to execute.",
                        },
                        "working_directory": {
                            "type": "string",
                            "description": "Absolute directory to run in. Defaults to the user's home.",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Maximum seconds before the process tree is killed.",
                            "minimum": 1,
                        },
                    },
                    "required": ["code", "timeout_seconds"],
                },
            ),
            Tool(
                name=self._tool_install_python_packages,
                description=(
                    "Install one or more Python packages into the brick's environment via "
                    "uv pip install. Accepts standard package specifiers (e.g. 'requests', "
                    "'requests==2.31.0', 'requests>=2.0,<3.0'). Returns uv's exit code, "
                    "stdout and stderr. Exceeding timeout_seconds kills the install."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "package_specifiers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Package specifiers to install in a single uv call.",
                            "minItems": 1,
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Maximum seconds before the install is killed.",
                            "minimum": 1,
                        },
                    },
                    "required": ["package_specifiers", "timeout_seconds"],
                },
            ),
        ]

        self._logger.debug(
            "get_tools_completed",
            conversation_id=str(conversation.id),
            tool_count=len(tools),
        )

        return tools

    async def handle_tool_request(
        self,
        name: str,
        parameters: str,
        conversation: Conversation,
    ) -> MessageContentToolResponse | None:
        """Handle tool request.

        Args:
            name: Tool name.
            parameters: Tool parameters as JSON string.
            conversation: Conversation object.

        Returns:
            Tool response.

        Raises:
            Error: If the brick is not ready, tool name is unknown or
                parameters are invalid.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )
        self._ensure_ready()

        try:
            parsed_parameters = json.loads(parameters)
        except json.JSONDecodeError as exception:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid JSON parameters: {exception}",
            )

        if not isinstance(parsed_parameters, dict):
            raise Error(ErrorCode.INVALID_ARGUMENT, "Parameters must be a JSON object")

        if name == self._tool_run_python_code:
            response = await self._handle_run_python_code(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_install_python_packages:
            response = await self._handle_install_python_packages(
                parameters=parsed_parameters, conversation=conversation
            )
        else:
            raise Error(ErrorCode.NOT_FOUND, f"Unknown tool: {name}")

        self._logger.debug(
            "handle_tool_request_completed",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        return response

    def _setup_synchronously(self) -> None:
        """Run the full setup chain synchronously inside a worker thread.

        Raises:
            Error: If the host OS is unsupported, download fails,
                hash verification fails or venv creation fails.
        """
        os_name = platform.system()
        arch_name = platform.machine()

        brick_folder = self._resolve_brick_folder(os_name=os_name)
        brick_folder.mkdir(parents=True, exist_ok=True)
        self._brick_folder = brick_folder

        uv_folder = brick_folder / self._uv_subfolder
        uv_folder.mkdir(parents=True, exist_ok=True)

        uv_binary_path = self._resolve_uv_binary_path(os_name=os_name, uv_folder=uv_folder)
        if not uv_binary_path.is_file():
            self._download_and_extract_uv(os_name=os_name, arch_name=arch_name, uv_folder=uv_folder)

        if not uv_binary_path.is_file():
            raise Error(
                ErrorCode.INTERNAL,
                f"uv binary not found after download: {uv_binary_path}",
            )
        self._uv_binary_path = uv_binary_path

        venv_path = brick_folder / self._venv_subfolder
        if not venv_path.is_dir():
            self._create_venv(uv_binary_path=uv_binary_path, venv_path=venv_path)
        self._venv_path = venv_path

        venv_python_path = self._resolve_venv_python_path(os_name=os_name, venv_path=venv_path)
        if not venv_python_path.is_file():
            raise Error(
                ErrorCode.INTERNAL,
                f"Venv python interpreter not found: {venv_python_path}",
            )
        self._venv_python_path = venv_python_path

    def _resolve_brick_folder(self, os_name: str) -> Path:
        """Pick the brick folder path for the host OS.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).

        Returns:
            Absolute path to the brick state folder.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            return self._macos_brick_folder
        elif os_name == self._os_windows:
            if not os.environ.get("LOCALAPPDATA"):
                raise Error(
                    ErrorCode.INTERNAL,
                    "LOCALAPPDATA environment variable is not set",
                )
            return self._windows_brick_folder
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _resolve_uv_binary_path(self, os_name: str, uv_folder: Path) -> Path:
        """Compute the expected uv binary path inside the uv folder.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            uv_folder: Root folder where uv is extracted.

        Returns:
            Absolute path to the uv executable.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            return uv_folder / self._uv_macos_binary_name
        elif os_name == self._os_windows:
            return uv_folder / self._uv_windows_binary_name
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _resolve_venv_python_path(self, os_name: str, venv_path: Path) -> Path:
        """Compute the path to the venv Python interpreter.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            venv_path: Root folder of the venv.

        Returns:
            Absolute path to the venv Python interpreter.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            return venv_path / "bin" / "python"
        elif os_name == self._os_windows:
            return venv_path / "Scripts" / "python.exe"
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _download_and_extract_uv(self, os_name: str, arch_name: str, uv_folder: Path) -> None:
        """Download the pinned uv release, verify SHA256 and extract the binary.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            arch_name: Result of platform.machine() (arm64 / x86_64).
            uv_folder: Destination folder for the extracted binary.

        Raises:
            Error: If the OS/arch is unsupported, the download fails or
                the SHA256 does not match.
        """
        asset_name, expected_sha256 = self._resolve_uv_asset(os_name=os_name, arch_name=arch_name)
        download_url = f"{self._uv_release_base_url}/{self._uv_version}/{asset_name}"

        self._logger.info("uv_download_started", asset=asset_name, url=download_url)

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(asset_name).suffix) as archive:
            archive_path = Path(archive.name)

        try:
            self._download_to_file(url=download_url, destination=archive_path)
            self._verify_sha256(file_path=archive_path, expected_sha256=expected_sha256)
            self._extract_uv_archive(
                os_name=os_name,
                arch_name=arch_name,
                archive_path=archive_path,
                uv_folder=uv_folder,
            )
            self._logger.info("uv_download_completed", asset=asset_name)
        finally:
            archive_path.unlink(missing_ok=True)

    def _resolve_uv_asset(self, os_name: str, arch_name: str) -> tuple[str, str]:
        """Pick the uv release asset and expected SHA256 for the host.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            arch_name: Result of platform.machine() (arm64 / x86_64).

        Returns:
            Tuple (asset_name, expected_sha256).

        Raises:
            Error: If the OS/arch combination is not supported.
        """
        if os_name == self._os_darwin and arch_name == self._arch_arm64:
            return self._uv_macos_arm64_asset, self._uv_macos_arm64_sha256
        elif os_name == self._os_darwin and arch_name == self._arch_x86_64:
            return self._uv_macos_x86_64_asset, self._uv_macos_x86_64_sha256
        elif os_name == self._os_windows and arch_name in {self._arch_x86_64, "AMD64"}:
            return self._uv_windows_x86_64_asset, self._uv_windows_x86_64_sha256
        else:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"Unsupported OS/arch combination: {os_name}/{arch_name}",
            )

    def _download_to_file(self, url: str, destination: Path) -> None:
        """Stream a URL to a destination file.

        Args:
            url: URL to download.
            destination: Path to write the response body to.

        Raises:
            Error: If the download fails for any reason.
        """
        # Python's default SSL trust store is empty on standalone Windows
        # builds (cafile=None, capath=None), so urlopen would fail with
        # "unable to get local issuer certificate". Point at certifi's
        # bundle for a cross-platform, reproducible trust root.
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        try:
            with (
                urllib.request.urlopen(url, context=ssl_context) as response,
                open(destination, "wb") as out,
            ):
                while True:
                    chunk = response.read(self._download_chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
        except Exception as exception:
            raise Error(ErrorCode.INTERNAL, f"Failed to download uv: {exception}")

    def _verify_sha256(self, file_path: Path, expected_sha256: str) -> None:
        """Verify the SHA256 of a file against an expected hex digest.

        Args:
            file_path: File to hash.
            expected_sha256: Expected lower-case hex digest.

        Raises:
            Error: If the hashes do not match.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as source:
            while True:
                chunk = source.read(self._download_chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)

        actual_sha256 = hasher.hexdigest()
        if actual_sha256 != expected_sha256:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"uv download SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}",
            )

    def _extract_uv_archive(
        self, os_name: str, arch_name: str, archive_path: Path, uv_folder: Path
    ) -> None:
        """Extract the uv binary from the verified archive into the uv folder.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            arch_name: Result of platform.machine() (arm64 / x86_64).
            archive_path: Path to the verified archive on disk.
            uv_folder: Destination folder for the uv binary.

        Raises:
            Error: If the OS is unsupported or the binary is missing
                from the archive.
        """
        if os_name == self._os_darwin:
            self._extract_uv_tarball(
                arch_name=arch_name, archive_path=archive_path, uv_folder=uv_folder
            )
        elif os_name == self._os_windows:
            self._extract_uv_zip(archive_path=archive_path, uv_folder=uv_folder)
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _extract_uv_tarball(self, arch_name: str, archive_path: Path, uv_folder: Path) -> None:
        """Extract the macOS uv binary from a tarball.

        Args:
            arch_name: Result of platform.machine() (arm64 / x86_64).
            archive_path: Path to the verified tarball.
            uv_folder: Destination folder for the uv binary.

        Raises:
            Error: If the arch is unsupported or the binary is missing
                from the archive.
        """
        if arch_name == self._arch_arm64:
            directory = self._uv_macos_arm64_directory
        elif arch_name == self._arch_x86_64:
            directory = self._uv_macos_x86_64_directory
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported arch: {arch_name}")

        member_name = f"{directory}/{self._uv_macos_binary_name}"
        destination = uv_folder / self._uv_macos_binary_name

        with tarfile.open(archive_path, mode="r:gz") as tar:
            try:
                member = tar.getmember(member_name)
            except KeyError:
                raise Error(
                    ErrorCode.INVALID_RESPONSE,
                    f"uv binary {member_name} missing from archive",
                )
            extracted = tar.extractfile(member)
            if extracted is None:
                raise Error(
                    ErrorCode.INVALID_RESPONSE,
                    f"Cannot read {member_name} from archive",
                )
            with extracted as source, open(destination, "wb") as out:
                shutil.copyfileobj(source, out)

        destination.chmod(0o755)

    def _extract_uv_zip(self, archive_path: Path, uv_folder: Path) -> None:
        """Extract the Windows uv binary from a zip.

        Args:
            archive_path: Path to the verified zip.
            uv_folder: Destination folder for the uv binary.

        Raises:
            Error: If the binary is missing from the archive.
        """
        destination = uv_folder / self._uv_windows_binary_name

        with zipfile.ZipFile(archive_path) as archive:
            candidate = next(
                (
                    name
                    for name in archive.namelist()
                    if name.endswith(f"/{self._uv_windows_binary_name}")
                    or name == self._uv_windows_binary_name
                ),
                None,
            )
            if candidate is None:
                raise Error(
                    ErrorCode.INVALID_RESPONSE,
                    f"uv binary {self._uv_windows_binary_name} missing from archive",
                )
            with archive.open(candidate) as source, open(destination, "wb") as out:
                shutil.copyfileobj(source, out)

    def _create_venv(self, uv_binary_path: Path, venv_path: Path) -> None:
        """Create the Python venv at the given path using uv.

        Args:
            uv_binary_path: Path to the uv executable.
            venv_path: Destination venv path.

        Raises:
            Error: If venv creation fails.
        """
        self._logger.info("venv_create_started", venv_path=str(venv_path))
        self._uv_binary_path = uv_binary_path
        completed = self._run_uv(["venv", str(venv_path)])
        if completed.returncode != 0:
            stderr = completed.stderr.decode(self._output_encoding, self._output_encoding_errors)
            raise Error(ErrorCode.INTERNAL, f"Failed to create venv: {stderr.strip()}")
        self._logger.info("venv_create_completed", venv_path=str(venv_path))

    def _run_uv(self, arguments: list[str]) -> "subprocess.CompletedProcess[bytes]":
        """Run a uv tooling command, repairing the binary once if it hangs.

        A uv process can get stuck in the kernel before its first instruction (seen on
        macOS right after the first launch of the freshly downloaded binary); every
        later exec of that same file then hangs too. Replacing the file with a fresh
        copy gives the kernel a new file to map, and re-downloading covers a copy that
        is itself unusable.

        Args:
            arguments: uv arguments, without the binary path.

        Returns:
            Completed process with captured output.

        Raises:
            Error: If uv is not initialized or stays unresponsive after the repair.
        """
        if self._uv_binary_path is None:
            raise Error(ErrorCode.INTERNAL, "uv path not initialized")

        completed = self._run_tooling_command([str(self._uv_binary_path), *arguments])
        if completed is not None:
            return completed

        self._logger.warning("uv_unresponsive", arguments=arguments)
        self._repair_uv_binary()

        completed = self._run_tooling_command([str(self._uv_binary_path), *arguments])
        if completed is None:
            raise Error(
                ErrorCode.INTERNAL,
                f"uv did not respond within {self._tooling_timeout_seconds}s even after repair",
            )
        return completed

    def _run_tooling_command(self, argv: list[str]) -> "subprocess.CompletedProcess[bytes] | None":
        # Deliberately no wait after the kill: a process stuck in the kernel never exits,
        # and waiting for it would freeze the caller exactly like the hang itself.
        process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=self._tooling_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            return None
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)

    def _repair_uv_binary(self) -> None:
        if self._uv_binary_path is None:
            raise Error(ErrorCode.INTERNAL, "uv path not initialized")

        repaired_path = self._uv_binary_path.with_name(
            self._uv_binary_path.name + self._uv_repair_suffix
        )
        try:
            shutil.copyfile(self._uv_binary_path, repaired_path)
            shutil.copymode(self._uv_binary_path, repaired_path)
            os.replace(repaired_path, self._uv_binary_path)
            self._logger.info("uv_repaired", strategy="copy")
        except OSError as exception:
            self._logger.warning("uv_repair_copy_failed", reason=str(exception))
            self._reinstall_uv_binary()
            return

        if self._run_tooling_command([str(self._uv_binary_path), "--version"]) is None:
            self._logger.warning("uv_repair_copy_unresponsive")
            self._reinstall_uv_binary()

    def _reinstall_uv_binary(self) -> None:
        if self._uv_binary_path is None:
            raise Error(ErrorCode.INTERNAL, "uv path not initialized")

        self._uv_binary_path.unlink(missing_ok=True)
        self._download_and_extract_uv(
            os_name=platform.system(),
            arch_name=platform.machine(),
            uv_folder=self._uv_binary_path.parent,
        )
        self._logger.info("uv_repaired", strategy="download")

    def _ensure_ready(self) -> None:
        """Raise the captured setup error if the brick is not ready.

        Raises:
            Error: The error captured during setup, if any.
        """
        if self._setup_error is not None:
            raise self._setup_error

    async def _read_python_version(self) -> str:
        """Run the venv Python with --version and return the trimmed output.

        Returns:
            Python version string (e.g. "Python 3.12.7").

        Raises:
            Error: If the version probe fails.
        """
        if self._venv_python_path is None:
            raise Error(ErrorCode.INTERNAL, "Venv Python path not initialized")

        completed = await asyncio.to_thread(
            self._run_tooling_command, [str(self._venv_python_path), "--version"]
        )
        if completed is None:
            raise Error(
                ErrorCode.INTERNAL,
                f"Venv Python did not respond within {self._tooling_timeout_seconds}s",
            )
        if completed.returncode != 0:
            stderr = completed.stderr.decode(self._output_encoding, self._output_encoding_errors)
            raise Error(ErrorCode.INTERNAL, f"Failed to read Python version: {stderr.strip()}")

        stdout = completed.stdout.decode(self._output_encoding, self._output_encoding_errors)
        return stdout.strip()

    async def _read_installed_packages(self) -> list[tuple[str, str]]:
        """List packages installed in the venv via uv pip list --format=json.

        Returns:
            List of (name, version) tuples, sorted by name.

        Raises:
            Error: If uv pip list fails or returns an unexpected payload.
        """
        if self._uv_binary_path is None or self._venv_python_path is None:
            raise Error(ErrorCode.INTERNAL, "uv/venv paths not initialized")

        completed = await asyncio.to_thread(
            self._run_uv,
            ["pip", "list", "--format=json", "--python", str(self._venv_python_path)],
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode(self._output_encoding, self._output_encoding_errors)
            raise Error(ErrorCode.INTERNAL, f"Failed to list packages: {stderr.strip()}")

        try:
            raw_packages = json.loads(
                completed.stdout.decode(self._output_encoding, self._output_encoding_errors)
            )
        except json.JSONDecodeError as exception:
            raise Error(
                ErrorCode.INVALID_RESPONSE, f"uv pip list returned invalid JSON: {exception}"
            )

        if not isinstance(raw_packages, list):
            raise Error(ErrorCode.INVALID_RESPONSE, "uv pip list did not return a list")

        packages: list[tuple[str, str]] = []
        for entry in raw_packages:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            version = entry.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            packages.append((name, version))

        packages.sort(key=lambda item: item[0].lower())
        return packages

    async def _handle_run_python_code(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Execute Python code and return its result as a tool response.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response containing exit_code, stdout, stderr and timed_out.

        Raises:
            Error: If parameters are invalid.
        """
        code = self._read_code(parameters=parameters)
        timeout_seconds = self._read_timeout_seconds(parameters=parameters)
        working_directory = self._read_working_directory(parameters=parameters)

        if self._venv_python_path is None:
            raise Error(ErrorCode.INTERNAL, "Venv Python path not initialized")

        self._logger.info(
            "run_python_code_started",
            conversation_id=str(conversation.id),
            working_directory=str(working_directory),
            timeout_seconds=timeout_seconds,
            code_length=len(code),
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding=self._output_encoding,
        ) as script_file:
            script_file.write(code)
            script_path = Path(script_file.name)

        try:
            exit_code, stdout, stderr, timed_out = await self._run_subprocess(
                os_name=platform.system(),
                argv=[str(self._venv_python_path), str(script_path)],
                working_directory=working_directory,
                timeout_seconds=timeout_seconds,
            )
        finally:
            script_path.unlink(missing_ok=True)

        self._logger.info(
            "run_python_code_completed",
            conversation_id=str(conversation.id),
            exit_code=exit_code,
            timed_out=timed_out,
            stdout_bytes=len(stdout.encode(self._output_encoding, self._output_encoding_errors)),
            stderr_bytes=len(stderr.encode(self._output_encoding, self._output_encoding_errors)),
        )

        payload = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
        }
        return MessageContentToolResponse(text=json.dumps(payload))

    async def _handle_install_python_packages(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Install Python packages and return uv's result as a tool response.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response containing exit_code, stdout, stderr and timed_out.

        Raises:
            Error: If parameters are invalid.
        """
        package_specifiers = self._read_package_specifiers(parameters=parameters)
        timeout_seconds = self._read_timeout_seconds(parameters=parameters)

        if self._uv_binary_path is None or self._venv_python_path is None:
            raise Error(ErrorCode.INTERNAL, "uv/venv paths not initialized")

        self._logger.info(
            "install_python_packages_started",
            conversation_id=str(conversation.id),
            package_specifiers=package_specifiers,
            timeout_seconds=timeout_seconds,
        )

        argv = [
            str(self._uv_binary_path),
            "pip",
            "install",
            "--python",
            str(self._venv_python_path),
            *package_specifiers,
        ]

        exit_code, stdout, stderr, timed_out = await self._run_subprocess(
            os_name=platform.system(),
            argv=argv,
            working_directory=Path.home(),
            timeout_seconds=timeout_seconds,
        )

        self._logger.info(
            "install_python_packages_completed",
            conversation_id=str(conversation.id),
            exit_code=exit_code,
            timed_out=timed_out,
            stdout_bytes=len(stdout.encode(self._output_encoding, self._output_encoding_errors)),
            stderr_bytes=len(stderr.encode(self._output_encoding, self._output_encoding_errors)),
        )

        payload = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
        }
        return MessageContentToolResponse(text=json.dumps(payload))

    def _read_code(self, parameters: dict[str, object]) -> str:
        raw_code = parameters.get("code")
        if not isinstance(raw_code, str) or not raw_code.strip():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: code",
            )
        return raw_code

    def _read_timeout_seconds(self, parameters: dict[str, object]) -> int:
        raw_timeout = parameters.get("timeout_seconds")
        if not isinstance(raw_timeout, int) or isinstance(raw_timeout, bool) or raw_timeout < 1:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: timeout_seconds",
            )
        return raw_timeout

    def _read_working_directory(self, parameters: dict[str, object]) -> Path:
        raw_working_directory = parameters.get("working_directory")
        if raw_working_directory is None:
            return Path.home()

        if not isinstance(raw_working_directory, str) or not raw_working_directory.strip():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Invalid parameter: working_directory",
            )

        working_directory = Path(raw_working_directory).expanduser()
        if not working_directory.is_dir():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Working directory does not exist: {working_directory}",
            )
        return working_directory

    def _read_package_specifiers(self, parameters: dict[str, object]) -> list[str]:
        raw_package_specifiers = parameters.get("package_specifiers")
        if not isinstance(raw_package_specifiers, list) or not raw_package_specifiers:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: package_specifiers",
            )

        package_specifiers: list[str] = []
        for raw_specifier in raw_package_specifiers:
            if not isinstance(raw_specifier, str):
                raise Error(
                    ErrorCode.INVALID_ARGUMENT,
                    "Each entry in package_specifiers must be a string",
                )
            specifier = raw_specifier.strip()
            if not specifier:
                raise Error(
                    ErrorCode.INVALID_ARGUMENT,
                    "package_specifiers must not contain empty entries",
                )
            package_specifiers.append(specifier)

        return package_specifiers

    async def _run_subprocess(
        self,
        os_name: str,
        argv: list[str],
        working_directory: Path,
        timeout_seconds: int,
    ) -> tuple[int, str, str, bool]:
        """Spawn a subprocess, enforce timeout and return decoded outputs.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            argv: Argument vector for the subprocess.
            working_directory: Directory to run in.
            timeout_seconds: Maximum number of seconds the process may run.

        Returns:
            Tuple (exit_code, stdout, stderr, timed_out). On timeout the
            process tree is force-killed and exit_code is set to -1.
        """
        process = await asyncio.to_thread(
            self._spawn_process,
            os_name=os_name,
            argv=argv,
            working_directory=working_directory,
        )

        try:
            raw_stdout, raw_stderr = await asyncio.wait_for(
                asyncio.to_thread(process.communicate),
                timeout=timeout_seconds,
            )
            exit_code = process.returncode
            timed_out = False
        except asyncio.TimeoutError:
            self._kill_process_tree(os_name=os_name, process=process)
            raw_stdout, raw_stderr = await asyncio.to_thread(process.communicate)
            exit_code = -1
            timed_out = True

        stdout = self._decode_and_truncate(raw_output=raw_stdout)
        stderr = self._decode_and_truncate(raw_output=raw_stderr)
        return exit_code, stdout, stderr, timed_out

    def _spawn_process(
        self, os_name: str, argv: list[str], working_directory: Path
    ) -> "subprocess.Popen[bytes]":
        """Spawn the subprocess with output captured as bytes.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            argv: Argument vector to spawn.
            working_directory: Directory to run in.

        Returns:
            Running Popen instance with stdout/stderr pipes.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            return subprocess.Popen(
                argv,
                cwd=str(working_directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        elif os_name == self._os_windows:
            return subprocess.Popen(
                argv,
                cwd=str(working_directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _kill_process_tree(self, os_name: str, process: "subprocess.Popen[bytes]") -> None:
        """Force-kill the process and any children it spawned.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            process: Running process to kill.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError as exception:
                self._logger.debug(
                    "kill_process_tree_already_exited",
                    pid=process.pid,
                    error=str(exception),
                )
        elif os_name == self._os_windows:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    check=False,
                    capture_output=True,
                )
            except OSError as exception:
                self._logger.debug(
                    "kill_process_tree_failed",
                    pid=process.pid,
                    error=str(exception),
                )
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _decode_and_truncate(self, raw_output: bytes) -> str:
        """Decode bytes as UTF-8 (replace errors) and cap to _output_max_bytes.

        Args:
            raw_output: Raw output bytes from the process.

        Returns:
            Decoded string, truncated with a marker if the limit is exceeded.
        """
        if len(raw_output) <= self._output_max_bytes:
            return raw_output.decode(self._output_encoding, self._output_encoding_errors)

        head = raw_output[: self._output_max_bytes].decode(
            self._output_encoding, self._output_encoding_errors
        )
        return head + self._output_truncated_marker
