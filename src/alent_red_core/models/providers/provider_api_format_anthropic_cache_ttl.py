from enum import Enum


class ProviderApiFormatAnthropicCacheTtl(str, Enum):
    """Anthropic cache TTL values."""

    DEFAULT = "default"
    MIN_5 = "5m"
    HOUR_1 = "1h"
