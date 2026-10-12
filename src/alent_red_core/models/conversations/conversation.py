from typing import TYPE_CHECKING, Optional
from uuid import UUID
from sqlalchemy import Column, ForeignKey, Index, UniqueConstraint
from sqlmodel import Field, Relationship

from ..base import Base
from ..types import ModelJSON, TrimmedNonEmptyStr
from ..errors import ErrorCode
from .conversation_sender import ConversationSender

if TYPE_CHECKING:
    from ..agents import Agent
    from ..messages import Message
    from ..gateways import Gateway


class Conversation(Base, table=True):
    """Conversation entity."""

    __table_args__ = (
        Index("index_conversation_updated_at", "updated_at"),
        Index("index_conversation_agent_id_updated_at", "agent_id", "updated_at"),
        UniqueConstraint(
            "gateway_id",
            "gateway_external_id",
            name="unique_conversation_gateway_id_gateway_external_id",
        ),
    )

    name: TrimmedNonEmptyStr | None = None
    processing: bool = False
    error_code: ErrorCode | None = None
    error_message: TrimmedNonEmptyStr | None = None
    context_tokens_count: int | None = None
    agent_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("agent.id", ondelete="SET NULL", onupdate="SET NULL")),
    )
    gateway_id: UUID | None = Field(
        default=None,
        sa_column=Column(ForeignKey("gateway.id", ondelete="SET NULL", onupdate="SET NULL")),
    )
    gateway_external_id: str | None = None
    sender: ConversationSender | None = Field(default=None, sa_type=ModelJSON(ConversationSender))

    agent: Optional["Agent"] = Relationship(back_populates="conversations")
    gateway: Optional["Gateway"] = Relationship(back_populates="conversations")
    messages: list["Message"] = Relationship(
        back_populates="conversation",
        sa_relationship_kwargs={"passive_deletes": True},
    )
