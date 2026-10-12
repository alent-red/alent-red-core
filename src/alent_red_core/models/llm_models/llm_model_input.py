from uuid import UUID
from pydantic import BaseModel, Field

from ..types import TrimmedNonEmptyStr
from .llm_model_image_detail import LlmModelImageDetail
from .llm_model_cache import LlmModelCache


class LlmModelInput(BaseModel):
    """LLM model input."""

    name: TrimmedNonEmptyStr
    model_id: TrimmedNonEmptyStr
    context_window_tokens_count: int = Field(gt=0)
    max_output_tokens_count: int = Field(gt=0)
    top_p: float = Field(ge=0)
    image_detail: LlmModelImageDetail
    cache: LlmModelCache
    provider_id: UUID
