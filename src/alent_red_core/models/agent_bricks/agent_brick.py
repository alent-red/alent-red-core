from typing import TYPE_CHECKING
from uuid import UUID
from sqlmodel import Field, Relationship, Column, ForeignKey
from sqlalchemy import UniqueConstraint

from ..base import Base

if TYPE_CHECKING:
    from ..agents import Agent
    from ..bricks import Brick


class AgentBrick(Base, table=True):
    """Agent-Brick association table."""

    __table_args__ = (
        UniqueConstraint("agent_id", "brick_id", name="unique_agent_brick_agent_id_brick_id"),
    )

    agent_id: UUID = Field(
        sa_column=Column(
            ForeignKey("agent.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        )
    )
    brick_id: UUID = Field(
        sa_column=Column(
            ForeignKey("brick.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        )
    )

    agent: "Agent" = Relationship(back_populates="agent_bricks")
    brick: "Brick" = Relationship(back_populates="agent_bricks")
