from typing import Literal

from pydantic import BaseModel

from ..types import UrlStr
from .provider_config_type import ProviderConfigType


class ProviderConfigLMStudio(BaseModel):
    """Configuration for LM Studio provider."""

    type: Literal[ProviderConfigType.LM_STUDIO] = ProviderConfigType.LM_STUDIO
    base_url: UrlStr
