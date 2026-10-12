from pydantic import BaseModel, Field

from .telegram_chat import TelegramChat
from .telegram_media_file import TelegramMediaFile
from .telegram_photo_size import TelegramPhotoSize
from .telegram_user import TelegramUser


class TelegramMessage(BaseModel):
    """A Telegram message."""

    message_id: int
    chat: TelegramChat
    from_user: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None
    photo: list[TelegramPhotoSize] = []
    document: TelegramMediaFile | None = None
    audio: TelegramMediaFile | None = None
    video: TelegramMediaFile | None = None
    voice: TelegramMediaFile | None = None
    video_note: TelegramMediaFile | None = None
    animation: TelegramMediaFile | None = None
    sticker: TelegramMediaFile | None = None
