from uuid import UUID
from pydantic import BaseModel

from .message import MessageContent


class MessageInput(BaseModel):
    """Message input."""

    content: MessageContent
    conversation_id: UUID
