from typing import Literal

from pydantic import BaseModel, Field

from .provider_api_format_anthropic_cache_ttl import ProviderApiFormatAnthropicCacheTtl
from .provider_api_format_type import ProviderApiFormatType


class ProviderApiFormatAnthropic(BaseModel):
    """Configuration for Anthropic API format."""

    type: Literal[ProviderApiFormatType.ANTHROPIC] = ProviderApiFormatType.ANTHROPIC
    reasoning_minimal_budget_tokens: int = Field(gt=0)
    reasoning_low_budget_tokens: int = Field(gt=0)
    reasoning_medium_budget_tokens: int = Field(gt=0)
    reasoning_high_budget_tokens: int = Field(gt=0)
    reasoning_xhigh_budget_tokens: int = Field(gt=0)
    cache_medium_ttl: ProviderApiFormatAnthropicCacheTtl
    cache_high_ttl: ProviderApiFormatAnthropicCacheTtl
    # Internal only (not in the proto): Anthropic reports prompt-cache tokens apart
    # from input_tokens, while servers that imitate the format (LM Studio) count them
    # inside. Set by the provider, never by the client.
    input_tokens_include_cache: bool
