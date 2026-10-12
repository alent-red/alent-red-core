from uuid import UUID
from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from .agent_reasoning import AgentReasoning
from .agent_verbosity import AgentVerbosity


class AgentInput(BaseModel):
    """Agent input."""

    name: TrimmedNonEmptyStr
    picture_file_key: TrimmedNonEmptyStr | None
    prompt: TrimmedNonEmptyStr | None
    attached_file_paths: list[TrimmedNonEmptyStr]
    reasoning: AgentReasoning
    verbosity: AgentVerbosity
    llm_model_id: UUID
    brick_ids: list[UUID]
