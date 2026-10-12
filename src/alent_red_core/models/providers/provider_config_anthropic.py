from typing import Literal

from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from .provider_config_type import ProviderConfigType


class ProviderConfigAnthropic(BaseModel):
    """Configuration for Anthropic provider."""

    type: Literal[ProviderConfigType.ANTHROPIC] = ProviderConfigType.ANTHROPIC
    api_key: TrimmedNonEmptyStr
