from typing import TYPE_CHECKING, Optional
from uuid import UUID
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Relationship

from ..base import Base
from ..types import ModelJSON, TrimmedNonEmptyStr
from .agent_reasoning import AgentReasoning
from .agent_verbosity import AgentVerbosity

if TYPE_CHECKING:
    from ..llm_models import LlmModel
    from ..conversations import Conversation
    from ..agent_bricks import AgentBrick
    from ..gateways import Gateway


class Agent(Base, table=True):
    """Agent entity."""

    name: TrimmedNonEmptyStr = Field(unique=True)
    picture_file_key: TrimmedNonEmptyStr | None = None
    prompt: TrimmedNonEmptyStr | None = None
    attached_file_paths: list[TrimmedNonEmptyStr] = Field(
        sa_type=ModelJSON(list[TrimmedNonEmptyStr])
    )
    reasoning: AgentReasoning
    verbosity: AgentVerbosity
    llm_model_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("llm_model.id", ondelete="SET NULL", onupdate="SET NULL")),
    )

    llm_model: Optional["LlmModel"] = Relationship(back_populates="agents")
    conversations: list["Conversation"] = Relationship(
        back_populates="agent",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    agent_bricks: list["AgentBrick"] = Relationship(
        back_populates="agent",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    gateways: list["Gateway"] = Relationship(
        back_populates="agent",
        sa_relationship_kwargs={"passive_deletes": True},
    )
