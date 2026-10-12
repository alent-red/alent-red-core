from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, Relationship, UniqueConstraint

from ..base import Base
from ..types import TrimmedNonEmptyStr
from .llm_model_image_detail import LlmModelImageDetail
from .llm_model_cache import LlmModelCache

if TYPE_CHECKING:
    from ..agents import Agent
    from ..providers import Provider


class LlmModel(Base, table=True):
    """LLM model entity."""

    __tablename__ = "llm_model"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="unique_llm_model_provider_id_model_id"),
        UniqueConstraint("provider_id", "name", name="unique_llm_model_provider_id_name"),
    )

    name: TrimmedNonEmptyStr
    model_id: TrimmedNonEmptyStr
    context_window_tokens_count: int = Field(gt=0)
    max_output_tokens_count: int = Field(gt=0)
    top_p: float = Field(ge=0)
    image_detail: LlmModelImageDetail
    cache: LlmModelCache
    provider_id: UUID = Field(
        sa_column=Column(
            ForeignKey("provider.id", ondelete="CASCADE", onupdate="CASCADE"),
            nullable=False,
        )
    )

    provider: "Provider" = Relationship(back_populates="llm_models")
    agents: list["Agent"] = Relationship(
        back_populates="llm_model",
        sa_relationship_kwargs={"passive_deletes": True},
    )
