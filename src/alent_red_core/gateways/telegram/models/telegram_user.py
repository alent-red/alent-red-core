from pydantic import BaseModel


class TelegramUser(BaseModel):
    """Sender of a Telegram message."""

    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
