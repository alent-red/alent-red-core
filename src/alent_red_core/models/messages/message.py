from typing import TYPE_CHECKING, Annotated, Union
from uuid import UUID
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Relationship, UniqueConstraint
from pydantic import Discriminator

from ..base import Base
from ..types import ModelJSON
from .message_content_internal import MessageContentInternal
from .message_content_user import MessageContentUser
from .message_content_ai import MessageContentAi
from .message_content_tool import MessageContentTool

if TYPE_CHECKING:
    from ..conversations import Conversation

MessageContent = Annotated[
    Union[MessageContentInternal, MessageContentUser, MessageContentAi, MessageContentTool],
    Discriminator("type"),
]


class Message(Base, table=True):
    """Message entity."""

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name="unique_message_conversation_id_sequence",
        ),
    )

    sequence: int
    content: MessageContent = Field(sa_type=ModelJSON(MessageContent))
    conversation_id: UUID = Field(
        sa_column=Column(
            ForeignKey("conversation.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        )
    )

    conversation: "Conversation" = Relationship(back_populates="messages")
