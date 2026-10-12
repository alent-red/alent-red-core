import asyncio
import os
import platform
from pathlib import Path
from uuid import UUID

from ...common import Logger
from ...models import (
    Blob,
    ConversationSender,
    Error,
    ErrorCode,
    GatewayConfig,
    GatewayConfigTelegram,
    GatewayConfigType,
    MessageContentUser,
)
from ...blob import BlobStorage
from ..base_gateway import BaseGateway
from ..gateway_reporter import GatewayReporter
from .models import TelegramMessage, TelegramUpdate, TelegramUser
from .telegram_client import TelegramClient

_OS_DARWIN = "Darwin"
_OS_WINDOWS = "Windows"
_MACOS_GATEWAY_FOLDER = (
    Path.home() / "Library" / "Application Support" / "AlentRed" / "telegram-gateway"
)
_WINDOWS_GATEWAY_FOLDER = Path(os.environ.get("LOCALAPPDATA", "")) / "AlentRed" / "telegram-gateway"
_TRANSIENT_RETRY_SECONDS = 1
_TYPING_ACTION = "typing"
_PICTURE_CONTENT_TYPE = "image/jpeg"
_PICTURE_FILE_NAME = "telegram_picture.jpg"
_ATTACHMENT_ONLY_TEXT = "The user sent these attached files"
_TRANSIENT_ERROR_CODES = (ErrorCode.TIMEOUT, ErrorCode.INVALID_RESPONSE)


class TelegramGateway(BaseGateway):
    """Telegram gateway using long polling.

    Receives updates via getUpdates, routes allowed user messages to the manager,
    and sends rendered messages back to Telegram chats.
    """

    def __init__(
        self,
        config: GatewayConfig,
        blob: BlobStorage,
        gateway_id: UUID,
        reporter: GatewayReporter,
    ):
        """Initialize the Telegram gateway.

        Args:
            config: Gateway configuration.
            blob: Blob storage instance.
            gateway_id: Identifier of this gateway.
            reporter: Reporter interface to report events back to the manager.
        """
        super().__init__(config, blob, gateway_id, reporter)
        self._client: TelegramClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._offset: int | None = None
        self._picture_keys: dict[int, str | None] = {}
        self._attachments_folder = self._resolve_attachments_folder()
        self._logger = Logger.get_logger("gateways.telegram.telegram_gateway")

    async def setup(self) -> None:
        """Create the client, prepare the attachments folder, and start polling."""
        self._logger.debug("setup_started", gateway_id=str(self._gateway_id))

        self._attachments_folder.mkdir(parents=True, exist_ok=True)
        self._client = TelegramClient(token=self._telegram_config().token)
        self._poll_task = asyncio.create_task(self._poll_loop())

        self._logger.debug("setup_completed", gateway_id=str(self._gateway_id))

    async def refresh(self, config: GatewayConfig) -> None:
        """Restart the gateway with an updated configuration.

        Args:
            config: Updated gateway configuration.
        """
        self._logger.debug("refresh_started", gateway_id=str(self._gateway_id))

        await self.clean()
        self._config = config
        self._offset = None
        self._picture_keys.clear()
        await self.setup()

        self._logger.debug("refresh_completed", gateway_id=str(self._gateway_id))

    async def clean(self) -> None:
        """Stop polling and close the client."""
        self._logger.debug("clean_started", gateway_id=str(self._gateway_id))

        if self._poll_task is not None:
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
            self._poll_task = None

        if self._client is not None:
            await self._client.close()
            self._client = None

        self._picture_keys.clear()

        self._logger.debug("clean_completed", gateway_id=str(self._gateway_id))

    async def handle_message(
        self, gateway_external_id: str, text: str | None, image_file_keys: list[str]
    ) -> None:
        """Send a message to a Telegram chat.

        Args:
            gateway_external_id: Telegram chat identifier as a string.
            text: Text to send, or None when only images are sent.
            image_file_keys: Blob keys of images to send.
        """
        client = self._require_client()
        chat_id = int(gateway_external_id)

        if text is not None:
            await client.send_message(chat_id, text)

        for image_file_key in image_file_keys:
            blob = await self._blob.read(image_file_key)
            if blob is None:
                continue
            await client.send_photo(chat_id, _PICTURE_FILE_NAME, blob.content)

    async def handle_conversation_processing(
        self, gateway_external_id: str, processing: bool
    ) -> None:
        """Show a typing indicator while a conversation is processing.

        Args:
            gateway_external_id: Telegram chat identifier as a string.
            processing: Whether the conversation is currently processing.
        """
        if not processing:
            return

        client = self._require_client()
        await client.send_chat_action(int(gateway_external_id), _TYPING_ACTION)

    async def _poll_loop(self) -> None:
        """Continuously poll Telegram, retrying transient failures forever."""
        client = self._require_client()

        while True:
            try:
                updates = await client.get_updates(self._offset)
                for update in updates:
                    await self._handle_update(update)
                    self._offset = update.update_id + 1
            except asyncio.CancelledError:
                raise
            except Error as error:
                if error.code in _TRANSIENT_ERROR_CODES:
                    self._logger.debug(
                        "poll_transient_error",
                        gateway_id=str(self._gateway_id),
                        error_code=error.code.value,
                    )
                    await asyncio.sleep(_TRANSIENT_RETRY_SECONDS)
                    continue
                self._logger.info(
                    "poll_fatal_error",
                    gateway_id=str(self._gateway_id),
                    error_code=error.code.value,
                )
                await self._reporter.handle_error(self._gateway_id, error)
                return

    async def _handle_update(self, update: TelegramUpdate) -> None:
        """Process a single update, routing allowed user messages to the manager.

        Args:
            update: The update to process.
        """
        message = update.message
        if message is None or message.from_user is None:
            return

        if not self._is_allowed(message.from_user):
            return

        attached_file_paths = await self._download_attachments(update.update_id, message)

        text = (message.text or "").strip()
        if not text:
            if not attached_file_paths:
                return
            text = _ATTACHMENT_ONLY_TEXT

        sender = await self._build_sender(message.from_user)

        await self._reporter.handle_message(
            self._gateway_id,
            str(message.chat.id),
            MessageContentUser(text=text, attached_file_paths=attached_file_paths),
            sender,
        )

    def _is_allowed(self, user: TelegramUser) -> bool:
        """Check whether a user is allowed to message the bot.

        Args:
            user: The Telegram user.

        Returns:
            True if the user is allowed, False otherwise.
        """
        config = self._telegram_config()
        if config.allow_all:
            return True
        if user.username is None:
            return False
        return user.username.strip().lower() in config.allowed_user_names

    async def _build_sender(self, user: TelegramUser) -> ConversationSender:
        """Build the conversation sender for a Telegram user.

        Args:
            user: The Telegram user.

        Returns:
            The conversation sender with name, username, and picture key.
        """
        name = self._build_name(user)

        user_name = None
        if user.username is not None:
            normalized_username = user.username.strip().lower()
            user_name = normalized_username or None

        picture_file_key = await self._resolve_picture_key(user.id)

        return ConversationSender(name=name, user_name=user_name, picture_file_key=picture_file_key)

    def _build_name(self, user: TelegramUser) -> str | None:
        """Build a display name from a user's first and last name.

        Args:
            user: The Telegram user.

        Returns:
            The composed name, or None when no name is available.
        """
        first_name = (user.first_name or "").strip()
        last_name = (user.last_name or "").strip()
        name_parts = [part for part in (first_name, last_name) if part]
        if not name_parts:
            return None
        return " ".join(name_parts)

    async def _resolve_picture_key(self, user_id: int) -> str | None:
        """Resolve a user's profile picture into a stored blob key.

        Fetches the picture once per user for this process lifetime, caching the
        result (including the absence of a picture) to avoid repeated lookups.

        Args:
            user_id: The Telegram user identifier.

        Returns:
            The blob key of the stored picture, or None when there is none.
        """
        if user_id in self._picture_keys:
            return self._picture_keys[user_id]

        picture_file_key = await self._fetch_picture_key(user_id)
        self._picture_keys[user_id] = picture_file_key
        return picture_file_key

    async def _fetch_picture_key(self, user_id: int) -> str | None:
        """Fetch and store a user's largest profile picture.

        Args:
            user_id: The Telegram user identifier.

        Returns:
            The blob key of the stored picture, or None when there is none.
        """
        client = self._require_client()

        profile_photos = await client.get_user_profile_photos(user_id)
        if not profile_photos.photos:
            return None

        largest_photo = profile_photos.photos[0][-1]
        telegram_file = await client.get_file(largest_photo.file_id)
        if telegram_file.file_path is None:
            return None

        content = await client.download_file(telegram_file.file_path)

        return await self._blob.save(
            Blob(
                content=content,
                content_type=_PICTURE_CONTENT_TYPE,
                file_name=_PICTURE_FILE_NAME,
            )
        )

    async def _download_attachments(self, update_id: int, message: TelegramMessage) -> list[str]:
        """Download a message's attachments to the attachments folder.

        Args:
            update_id: The update identifier, used to prefix file names.
            message: The Telegram message.

        Returns:
            The list of absolute paths of the downloaded attachments.
        """
        file_ids = self._collect_file_ids(message)

        attached_file_paths: list[str] = []
        for file_index, file_id in enumerate(file_ids):
            path = await self._download_attachment(update_id, file_index, file_id)
            if path is not None:
                attached_file_paths.append(path)

        return attached_file_paths

    def _collect_file_ids(self, message: TelegramMessage) -> list[str]:
        """Collect the downloadable file ids present on a message.

        Args:
            message: The Telegram message.

        Returns:
            The file ids of every media attachment, photo taken at its largest size.
        """
        file_ids: list[str] = []

        if message.photo:
            file_ids.append(message.photo[-1].file_id)

        media_files = (
            message.document,
            message.audio,
            message.video,
            message.voice,
            message.video_note,
            message.animation,
            message.sticker,
        )
        for media_file in media_files:
            if media_file is not None:
                file_ids.append(media_file.file_id)

        return file_ids

    async def _download_attachment(
        self, update_id: int, file_index: int, file_id: str
    ) -> str | None:
        """Download a single attachment to disk.

        Args:
            update_id: The update identifier, used to prefix the file name.
            file_index: Index of the file within the message, to avoid conflicts.
            file_id: Identifier of the file to download.

        Returns:
            The absolute path of the downloaded file, or None when unavailable.
        """
        client = self._require_client()

        telegram_file = await client.get_file(file_id)
        if telegram_file.file_path is None:
            return None

        content = await client.download_file(telegram_file.file_path)

        source_name = Path(telegram_file.file_path).name
        destination_name = f"{update_id}_{file_index}_{source_name}"
        destination_path = self._attachments_folder / destination_name
        destination_path.write_bytes(content)

        return str(destination_path)

    def _telegram_config(self) -> GatewayConfigTelegram:
        """Narrow the gateway config to the Telegram variant.

        Returns:
            The Telegram gateway configuration.

        Raises:
            Error: If the config is not a Telegram configuration.
        """
        if self._config.type != GatewayConfigType.TELEGRAM:
            raise Error(
                ErrorCode.INTERNAL,
                f"TelegramGateway requires a Telegram config, got {self._config.type}",
            )
        return self._config

    def _require_client(self) -> TelegramClient:
        """Return the active client, raising if the gateway is not set up.

        Returns:
            The active Telegram client.

        Raises:
            Error: If the client is not initialized.
        """
        if self._client is None:
            raise Error(ErrorCode.INTERNAL, "TelegramGateway client is not initialized")
        return self._client

    def _resolve_attachments_folder(self) -> Path:
        """Pick the attachments folder for the host OS.

        Returns:
            Absolute path to the attachments folder.

        Raises:
            Error: If the host operating system is not supported.
        """
        os_name = platform.system()
        if os_name == _OS_DARWIN:
            return _MACOS_GATEWAY_FOLDER
        if os_name == _OS_WINDOWS:
            if not os.environ.get("LOCALAPPDATA"):
                raise Error(
                    ErrorCode.INTERNAL,
                    "LOCALAPPDATA environment variable is not set",
                )
            return _WINDOWS_GATEWAY_FOLDER
        raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")
