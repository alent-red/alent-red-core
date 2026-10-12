from pydantic import BaseModel


class ConversationSender(BaseModel):
    """Sender identity of a conversation originating from a gateway."""

    name: str | None = None
    user_name: str | None = None
    picture_file_key: str | None = None
