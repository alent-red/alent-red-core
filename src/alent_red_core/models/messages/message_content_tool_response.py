from pydantic import BaseModel
from ..types import TrimmedNonEmptyStr


class MessageContentToolResponse(BaseModel):
    """Tool response content with optional text and image file keys."""

    text: str | None = None
    image_file_keys: list[TrimmedNonEmptyStr] = []
