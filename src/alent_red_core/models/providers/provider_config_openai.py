from typing import Literal

from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from .provider_config_type import ProviderConfigType


class ProviderConfigOpenAI(BaseModel):
    """Configuration for OpenAI provider."""

    type: Literal[ProviderConfigType.OPENAI] = ProviderConfigType.OPENAI
    api_key: TrimmedNonEmptyStr
