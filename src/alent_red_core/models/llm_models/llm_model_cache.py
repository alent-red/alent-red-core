from enum import Enum


class LlmModelCache(str, Enum):
    """Cache duration for LLM model responses."""

    DEFAULT = "default"
    MEDIUM = "medium"
    HIGH = "high"
