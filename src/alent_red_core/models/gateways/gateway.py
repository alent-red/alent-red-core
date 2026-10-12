from typing import TYPE_CHECKING, Annotated, Union
from uuid import UUID
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Relationship, UniqueConstraint
from pydantic import Discriminator

from ..base import Base
from ..types import ModelJSON, TrimmedNonEmptyStr
from ..errors import ErrorCode
from .gateway_config_telegram import GatewayConfigTelegram

if TYPE_CHECKING:
    from ..agents import Agent
    from ..conversations import Conversation

GatewayConfig = Annotated[
    Union[GatewayConfigTelegram],
    Discriminator("type"),
]


class Gateway(Base, table=True):
    """Gateway entity."""

    __table_args__ = (UniqueConstraint("name", "agent_id", name="unique_gateway_name_agent_id"),)

    name: TrimmedNonEmptyStr
    send_detailed_messages: bool
    error_code: ErrorCode | None = None
    error_message: TrimmedNonEmptyStr | None = None
    config: GatewayConfig = Field(sa_type=ModelJSON(GatewayConfig))
    agent_id: UUID = Field(
        sa_column=Column(
            ForeignKey("agent.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        )
    )

    agent: "Agent" = Relationship(back_populates="gateways")
    conversations: list["Conversation"] = Relationship(
        back_populates="gateway",
        sa_relationship_kwargs={"passive_deletes": True},
    )
