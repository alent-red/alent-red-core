from enum import Enum


class LlmModelImageDetail(str, Enum):
    """Image detail level for LLM model vision capabilities."""

    DEFAULT = "default"
    LOW = "low"
    HIGH = "high"
