from pydantic import BaseModel, Field

from ..types import TrimmedNonEmptyStr
from .provider_config_anthropic import ProviderConfigAnthropic
from .provider_config_custom import ProviderConfigCustom
from .provider_config_lm_studio import ProviderConfigLMStudio
from .provider_config_openai import ProviderConfigOpenAI


class ProviderInput(BaseModel):
    """Provider input."""

    name: TrimmedNonEmptyStr
    config: (
        ProviderConfigAnthropic
        | ProviderConfigOpenAI
        | ProviderConfigLMStudio
        | ProviderConfigCustom
    )
