from typing import Annotated, Literal, Union

from pydantic import BaseModel, Discriminator

from ..types import TrimmedNonEmptyStr, UrlStr
from .provider_api_format_anthropic import ProviderApiFormatAnthropic
from .provider_api_format_openai_chat_completions import ProviderApiFormatOpenAiChatCompletions
from .provider_api_format_openai_responses import ProviderApiFormatOpenAiResponses
from .provider_config_type import ProviderConfigType

ProviderApiFormat = Annotated[
    Union[
        ProviderApiFormatAnthropic,
        ProviderApiFormatOpenAiChatCompletions,
        ProviderApiFormatOpenAiResponses,
    ],
    Discriminator("type"),
]


class ProviderConfigCustom(BaseModel):
    """Configuration for custom provider."""

    type: Literal[ProviderConfigType.CUSTOM] = ProviderConfigType.CUSTOM
    base_url: UrlStr
    api_key: TrimmedNonEmptyStr | None
    api_format: ProviderApiFormat
