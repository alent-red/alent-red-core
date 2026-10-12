from typing import Literal
from pydantic import BaseModel

from .message_content_type import MessageContentType


class MessageContentAi(BaseModel):
    """AI message content."""

    type: Literal[MessageContentType.AI] = MessageContentType.AI
    text: str
    processing: bool
