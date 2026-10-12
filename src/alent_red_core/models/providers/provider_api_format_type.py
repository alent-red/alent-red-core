from enum import Enum


class ProviderApiFormatType(str, Enum):
    """Provider API format type enum."""

    ANTHROPIC = "anthropic"
    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    OPENAI_RESPONSES = "openai_responses"
