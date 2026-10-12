from typing import Literal
from pydantic import BaseModel

from .message_content_type import MessageContentType
from ..types import TrimmedNonEmptyStr


class MessageContentInternal(BaseModel):
    """Internal message content."""

    type: Literal[MessageContentType.INTERNAL] = MessageContentType.INTERNAL
    text: TrimmedNonEmptyStr
