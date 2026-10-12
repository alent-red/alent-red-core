from pydantic import BaseModel

from .telegram_message import TelegramMessage


class TelegramUpdate(BaseModel):
    """A single update returned by getUpdates."""

    update_id: int
    message: TelegramMessage | None = None
