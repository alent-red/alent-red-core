from pydantic import BaseModel, Field


class Blob(BaseModel):
    """Blob content with metadata."""

    content: bytes = Field(min_length=1)
    content_type: str = Field(min_length=1)
    file_name: str | None = None
