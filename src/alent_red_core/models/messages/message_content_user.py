from typing import Literal
from pydantic import BaseModel

from .message_content_type import MessageContentType
from ..types import TrimmedNonEmptyStr


class MessageContentUser(BaseModel):
    """User message content."""

    type: Literal[MessageContentType.USER] = MessageContentType.USER
    text: TrimmedNonEmptyStr
    attached_file_paths: list[TrimmedNonEmptyStr]
