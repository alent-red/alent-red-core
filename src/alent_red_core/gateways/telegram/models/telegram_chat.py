from pydantic import BaseModel


class TelegramChat(BaseModel):
    """Chat a Telegram message belongs to."""

    id: int
