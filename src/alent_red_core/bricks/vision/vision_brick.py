import asyncio
import json
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps, UnidentifiedImageError

from ..base_brick import BaseBrick
from ...common import Logger
from ...models import (
    Blob,
    BrickConfigVision,
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


class VisionBrick(BaseBrick):
    """Vision brick letting the LLM look at image files stored on the host."""

    _identifier = "vision"

    _tool_view_images = "view_images"

    _supported_formats = ("PNG", "JPEG", "GIF", "WEBP", "BMP", "TIFF")
    _heic_brands = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1")

    _image_max_edge = 1920
    _image_format = "JPEG"
    _image_quality = 80
    _image_content_type = "image/jpeg"
    _image_file_extension = "jpg"
    _flatten_background_color = (255, 255, 255)

    _reason_not_absolute = "path must be absolute"
    _reason_not_found = "file not found"
    _reason_not_a_file = "not a file"
    _reason_unsupported_heic = "unsupported format (HEIC)"
    _reason_unsupported = "unsupported format (not a raster image)"
    _reason_cannot_decode = "cannot be decoded"

    def __init__(
        self,
        config: BrickConfigVision,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize vision brick.

        Args:
            config: Vision brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        super().__init__(config, looper, bricks, providers, database, blob)
        self._logger = Logger.get_logger("bricks.vision.vision_brick")

    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        return self._identifier

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick.

        Args:
            conversation: Conversation object.

        Returns:
            List with the view_images tool.
        """
        supported = ", ".join(self._supported_formats)
        return [
            Tool(
                name=self._tool_view_images,
                description=(
                    "Look at one or more image files stored on this computer. Each image is "
                    "returned to you so you can see it. Only raster images are supported "
                    f"({supported}); convert other formats first. Give absolute paths."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "description": "Absolute paths of the image files to view.",
                            "items": {"type": "string"},
                            "minItems": 1,
                        }
                    },
                    "required": ["paths"],
                },
            )
        ]

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
            Tool response with every image when all paths are valid, or a text listing
            each failing path with its reason and how to fix it.

        Raises:
            Error: If tool name is unknown, parameters are invalid, or a file cannot be
                rendered after passing validation.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        if name != self._tool_view_images:
            raise Error(ErrorCode.NOT_FOUND, f"Unknown tool: {name}")

        paths = self._read_paths(parameters=parameters)

        failures = await asyncio.to_thread(self._validate_paths, paths)
        if failures:
            self._logger.info(
                "view_images_rejected",
                conversation_id=str(conversation.id),
                path_count=len(paths),
                failure_count=len(failures),
            )
            return MessageContentToolResponse(text=self._build_failure_text(paths, failures))

        blob_keys: list[str] = []
        for path in paths:
            jpeg_bytes = await asyncio.to_thread(self._render_image, path)
            blob_keys.append(
                await self._blob.save(
                    Blob(
                        content=jpeg_bytes,
                        content_type=self._image_content_type,
                        file_name=f"{path.stem}.{self._image_file_extension}",
                    )
                )
            )

        self._logger.info(
            "view_images_completed",
            conversation_id=str(conversation.id),
            path_count=len(paths),
        )

        return MessageContentToolResponse(image_file_keys=blob_keys)

    def _read_paths(self, parameters: str) -> list[Path]:
        try:
            parsed_parameters = json.loads(parameters)
        except json.JSONDecodeError as exception:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Invalid JSON parameters: {exception}")

        if not isinstance(parsed_parameters, dict):
            raise Error(ErrorCode.INVALID_ARGUMENT, "Parameters must be a JSON object")

        raw_paths = parsed_parameters.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            raise Error(ErrorCode.INVALID_ARGUMENT, "Missing or invalid required parameter: paths")

        paths: list[Path] = []
        for raw_path in raw_paths:
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise Error(
                    ErrorCode.INVALID_ARGUMENT, "Each entry in paths must be a non-empty string"
                )
            paths.append(self._expand_user(Path(raw_path.strip())))
        return paths

    def _expand_user(self, path: Path) -> Path:
        # A host without a resolvable home directory keeps the path as given; it then
        # fails validation as a non-absolute path instead of crashing the tool.
        try:
            return path.expanduser()
        except RuntimeError:
            return path

    def _validate_paths(self, paths: list[Path]) -> list[tuple[Path, str]]:
        failures: list[tuple[Path, str]] = []
        for path in paths:
            reason = self._validate_path(path)
            if reason is not None:
                failures.append((path, reason))
        return failures

    def _validate_path(self, path: Path) -> str | None:
        if not path.is_absolute():
            return self._reason_not_absolute
        if not path.exists():
            return self._reason_not_found
        if not path.is_file():
            return self._reason_not_a_file

        try:
            with Image.open(path) as image:
                if image.format not in self._supported_formats:
                    return self._reason_unsupported
                image.load()
        except UnidentifiedImageError:
            return (
                self._reason_unsupported_heic if self._is_heic(path) else self._reason_unsupported
            )
        except OSError:
            return self._reason_cannot_decode

        return None

    def _is_heic(self, path: Path) -> bool:
        # ISO base media files carry an "ftyp" box at offset 4 followed by the brand.
        with path.open("rb") as handle:
            header = handle.read(12)
        return header[4:8] == b"ftyp" and header[8:12] in self._heic_brands

    def _build_failure_text(self, paths: list[Path], failures: list[tuple[Path, str]]) -> str:
        lines = [f"Could not view {len(failures)} of {len(paths)} images."]
        lines.extend(f"- {path}: {reason}" for path, reason in failures)
        lines.append(
            f"Supported formats: {', '.join(self._supported_formats)}. Convert the failing "
            f"files to one of these formats, or fix their paths, then call "
            f"{self._identifier} {self._tool_view_images} again."
        )
        return "\n".join(lines)

    def _render_image(self, path: Path) -> bytes:
        """Load an image, flatten transparency, downscale, encode as JPEG.

        Args:
            path: Validated image path.

        Returns:
            JPEG bytes at most _image_max_edge on the longest side.
        """
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source) or source
            image = self._flatten(image)

            if max(image.size) > self._image_max_edge:
                image.thumbnail(
                    (self._image_max_edge, self._image_max_edge), Image.Resampling.LANCZOS
                )

            buffer = BytesIO()
            image.save(buffer, format=self._image_format, quality=self._image_quality)
            return buffer.getvalue()

    def _flatten(self, image: Image.Image) -> Image.Image:
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        if not has_alpha:
            return image.convert("RGB")

        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, self._flatten_background_color)
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
