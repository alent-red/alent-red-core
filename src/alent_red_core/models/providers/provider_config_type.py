from enum import Enum


class ProviderConfigType(str, Enum):
    """Provider configuration type enumeration."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    LM_STUDIO = "lm_studio"
    CUSTOM = "custom"
