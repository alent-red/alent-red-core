from pydantic import BaseModel

from ..messages import MessageContent
from .llm_usage import LlmUsage


class LlmResponse(BaseModel):
    """Result of a non-streaming LLM call: the contents produced and the usage."""

    contents: list[MessageContent]
    usage: LlmUsage
