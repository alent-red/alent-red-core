from uuid import UUID
from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from ..errors import ErrorCode
from .conversation_sender import ConversationSender


class ConversationInput(BaseModel):
    """Conversation input."""

    name: TrimmedNonEmptyStr | None
    agent_id: UUID | None
    processing: bool
    error_code: ErrorCode | None
    error_message: TrimmedNonEmptyStr | None
    context_tokens_count: int | None
    gateway_id: UUID | None
    gateway_external_id: str | None
    sender: ConversationSender | None
