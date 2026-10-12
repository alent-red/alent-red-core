from typing import Literal
from pydantic import BaseModel

from .message_content_type import MessageContentType
from .message_content_tool_response import MessageContentToolResponse
from ..types import TrimmedNonEmptyStr
from ..errors import ErrorCode


class MessageContentTool(BaseModel):
    """Tool request/result message content."""

    type: Literal[MessageContentType.TOOL] = MessageContentType.TOOL
    name: TrimmedNonEmptyStr
    processing: bool
    error: ErrorCode | None
    request: str
    response: MessageContentToolResponse | None
    llm_id: TrimmedNonEmptyStr  # LLM provider's tool call ID for mapping
    turn_id: TrimmedNonEmptyStr  # Links tools to their AI message turn
