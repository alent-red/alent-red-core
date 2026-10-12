from abc import ABC
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field


class Base(SQLModel, ABC, table=False):
    """Abstract base class for all models with id and timestamps."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )
