import asyncio
import datetime
import json
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..base_brick import BaseBrick
from ...common import Logger
from ...models import (
    BrickConfigSystem,
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


class SystemBrick(BaseBrick):
    """System brick exposing host environment context to the LLM."""

    _identifier = "system"

    _os_darwin = "Darwin"
    _os_windows = "Windows"

    _macos_app_roots = ["/Applications", "/System/Applications", "~/Applications"]
    _windows_app_roots = ["C:\\Program Files", "C:\\Program Files (x86)"]

    _prompt_template = (
        "Today is: {{DAY}}\n"
        "Timezone: {{TIMEZONE}}\n"
        "You are working inside this OS: {{OS}}\n"
        "Installed apps:\n"
        "- {{APPS_PATHS}}"
    )
    _apps_paths_separator = "\n- "

    _tool_run_terminal_command = "run_terminal_command"
    _tool_get_current_date_time = "get_current_date_time"

    _output_max_bytes = 50_000
    _output_truncated_marker = "\n... [output truncated]"
    _output_encoding = "utf-8"
    _output_encoding_errors = "replace"

    def __init__(
        self,
        config: BrickConfigSystem,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize system brick.

        Args:
            config: System brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        super().__init__(config, looper, bricks, providers, database, blob)
        self._logger = Logger.get_logger("bricks.system.system_brick")

    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        return self._identifier

    async def get_prompt(self, conversation: Conversation) -> str | None:
        """Build a prompt describing the host environment.

        Args:
            conversation: Conversation object.

        Returns:
            Rendered system prompt.

        Raises:
            Error: If the host operating system is not supported.
        """
        self._logger.debug("get_prompt_started", conversation_id=str(conversation.id))

        os_name = platform.system()
        day = self._build_day()
        timezone = self._build_timezone()
        os_description = platform.platform()
        apps_paths = self._apps_paths_separator.join(self._list_apps(os_name=os_name))

        prompt = (
            self._prompt_template.replace("{{DAY}}", day)
            .replace("{{TIMEZONE}}", timezone)
            .replace("{{OS}}", os_description)
            .replace("{{APPS_PATHS}}", apps_paths)
        )

        self._logger.debug(
            "get_prompt_completed",
            conversation_id=str(conversation.id),
            os=os_description,
        )

        return prompt

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick.

        Args:
            conversation: Conversation object.

        Returns:
            List of tools.

        Raises:
            Error: If the host operating system is not supported.
        """
        self._logger.debug("get_tools_started", conversation_id=str(conversation.id))

        os_name = platform.system()
        if os_name == self._os_darwin:
            shell_description = "bash"
            terminal_command_description = (
                "Bash terminal command to run. Pipes, redirects and '&&' are supported."
            )
        elif os_name == self._os_windows:
            shell_description = "PowerShell"
            terminal_command_description = (
                "PowerShell terminal command to run. Pipes, redirects and ';' are supported."
            )
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

        tools = [
            Tool(
                name=self._tool_run_terminal_command,
                description=(
                    f"Run a {shell_description} terminal command and return its exit code, "
                    "stdout and stderr. Each call uses a fresh shell, so no state (cwd, env "
                    "vars) carries over; chain operations in a single terminal command "
                    "instead. Output is captured separately and truncated past 50000 bytes "
                    "per stream. Exceeding timeout_seconds kills the process tree and "
                    "returns timed_out=true with any captured output."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "terminal_command": {
                            "type": "string",
                            "description": terminal_command_description,
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
                    "required": ["terminal_command", "timeout_seconds"],
                },
            ),
            Tool(
                name=self._tool_get_current_date_time,
                description=(
                    "Get the current local date, day of week and timezone. Call this "
                    "whenever you need the precise current time, especially before "
                    "scheduling notifications relative to 'now'."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
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
            Error: If tool name is unknown or parameters are invalid.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        try:
            parsed_parameters = json.loads(parameters)
        except json.JSONDecodeError as exception:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid JSON parameters: {exception}",
            )

        if not isinstance(parsed_parameters, dict):
            raise Error(ErrorCode.INVALID_ARGUMENT, "Parameters must be a JSON object")

        if name == self._tool_run_terminal_command:
            response = await self._handle_run_terminal_command(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_get_current_date_time:
            response = await self._handle_get_current_date_time(conversation=conversation)
        else:
            raise Error(ErrorCode.NOT_FOUND, f"Unknown tool: {name}")

        self._logger.debug(
            "handle_tool_request_completed",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        return response

    async def _handle_run_terminal_command(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Execute a terminal command and return its result as a tool response.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response containing exit_code, stdout, stderr and timed_out.

        Raises:
            Error: If parameters are invalid.
        """
        terminal_command = self._read_terminal_command(parameters=parameters)
        timeout_seconds = self._read_timeout_seconds(parameters=parameters)
        working_directory = self._read_working_directory(parameters=parameters)

        self._logger.info(
            "run_terminal_command_started",
            conversation_id=str(conversation.id),
            terminal_command=terminal_command,
            working_directory=str(working_directory),
            timeout_seconds=timeout_seconds,
        )

        exit_code, stdout, stderr, timed_out = await self._run_terminal_command(
            os_name=platform.system(),
            terminal_command=terminal_command,
            working_directory=working_directory,
            timeout_seconds=timeout_seconds,
        )

        self._logger.info(
            "run_terminal_command_completed",
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

    async def _handle_get_current_date_time(
        self, conversation: Conversation
    ) -> MessageContentToolResponse:
        """Return the current local date, day of week and timezone.

        Args:
            conversation: Conversation object.

        Returns:
            Tool response containing date_time, day and timezone.
        """
        self._logger.debug("get_current_date_time_started", conversation_id=str(conversation.id))

        now = datetime.datetime.now().astimezone()
        payload = {
            "date_time": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "day": now.strftime("%A"),
            "timezone": self._build_timezone(),
        }

        self._logger.debug(
            "get_current_date_time_completed",
            conversation_id=str(conversation.id),
            date_time=payload["date_time"],
        )

        return MessageContentToolResponse(text=json.dumps(payload))

    def _read_terminal_command(self, parameters: dict[str, object]) -> str:
        raw_terminal_command = parameters.get("terminal_command")
        if not isinstance(raw_terminal_command, str):
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: terminal_command",
            )

        terminal_command = raw_terminal_command.strip()
        if not terminal_command:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: terminal_command",
            )
        return terminal_command

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

    async def _run_terminal_command(
        self,
        os_name: str,
        terminal_command: str,
        working_directory: Path,
        timeout_seconds: int,
    ) -> tuple[int, str, str, bool]:
        """Spawn the terminal command, enforce timeout, return decoded outputs.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            terminal_command: Shell terminal command line to execute.
            working_directory: Directory to run the terminal command in.
            timeout_seconds: Maximum number of seconds the terminal command may run.

        Returns:
            Tuple (exit_code, stdout, stderr, timed_out). On timeout the
            process tree is force-killed and exit_code is set to -1.
        """
        process = await asyncio.to_thread(
            self._spawn_process,
            os_name=os_name,
            terminal_command=terminal_command,
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
        self, os_name: str, terminal_command: str, working_directory: Path
    ) -> "subprocess.Popen[bytes]":
        """Spawn the shell subprocess for the host OS with output captured as bytes.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).
            terminal_command: Shell terminal command line to execute.
            working_directory: Directory to run the terminal command in.

        Returns:
            Running Popen instance with stdout/stderr pipes.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            return subprocess.Popen(
                ["/bin/bash", "-c", terminal_command],
                cwd=str(working_directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        elif os_name == self._os_windows:
            return subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command", terminal_command],
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

    def _build_day(self) -> str:
        """Build the current local date in long human form.

        Returns:
            Long human date (e.g. "Saturday, May 23, 2026").
        """
        # Day-without-zero-padding is not portable in strftime: %-d is GNU/BSD,
        # %#d is Microsoft. Composing the string with int(now.day) sidesteps
        # the libc difference and gives the same result on every OS.
        now = datetime.datetime.now().astimezone()
        return f"{now.strftime('%A, %B')} {now.day}, {now.year}"

    def _build_timezone(self) -> str:
        """Build the local timezone offset string.

        Returns:
            UTC offset string (e.g. "UTC+2", "UTC-5", "UTC+5:30").
        """
        offset = datetime.datetime.now().astimezone().utcoffset()
        if offset is None:
            return "UTC+0"

        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        hours, remainder = divmod(abs(total_seconds), 3600)
        minutes = remainder // 60

        if minutes == 0:
            return f"UTC{sign}{hours}"
        return f"UTC{sign}{hours}:{minutes:02d}"

    def _list_apps(self, os_name: str) -> list[str]:
        """List installed application paths for the given OS.

        Args:
            os_name: Result of platform.system() (Darwin or Windows).

        Returns:
            Sorted, deduplicated list of full application paths.

        Raises:
            Error: If the host operating system is not supported.
        """
        if os_name == self._os_darwin:
            return self._list_macos_apps()
        elif os_name == self._os_windows:
            return self._list_windows_apps()
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")

    def _list_macos_apps(self) -> list[str]:
        """Scan macOS application roots for .app bundles.

        Returns:
            Sorted, deduplicated list of full .app paths.
        """
        paths: set[str] = set()
        for root in self._macos_app_roots:
            for path in self._scan_directory(root=root, suffix=".app"):
                paths.add(path)

        return sorted(paths)

    def _list_windows_apps(self) -> list[str]:
        """Scan Windows program-files roots one level deep.

        Returns:
            Sorted, deduplicated list of full installation directory paths.
        """
        paths: set[str] = set()
        for root in self._windows_app_roots:
            for path in self._scan_directory(root=root, suffix=None):
                paths.add(path)

        return sorted(paths)

    def _scan_directory(self, root: str, suffix: str | None) -> list[str]:
        """List immediate children of a directory, optionally filtering by suffix.

        Args:
            root: Directory path to scan (supports ~ expansion).
            suffix: Required name suffix (e.g. ".app") or None for no filter.

        Returns:
            Full paths of matching immediate children. Empty if the root is
            missing or unreadable.
        """
        expanded_root = Path(root).expanduser()
        if not expanded_root.is_dir():
            return []

        try:
            entries = os.listdir(expanded_root)
        except OSError as exception:
            self._logger.debug(
                "scan_directory_failed", root=str(expanded_root), error=str(exception)
            )
            return []

        if suffix is None:
            return [str(expanded_root / entry) for entry in entries]
        return [str(expanded_root / entry) for entry in entries if entry.endswith(suffix)]
