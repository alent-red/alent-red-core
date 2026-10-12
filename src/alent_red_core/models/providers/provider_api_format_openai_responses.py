from typing import Literal

from pydantic import BaseModel

from .provider_api_format_type import ProviderApiFormatType


class ProviderApiFormatOpenAiResponses(BaseModel):
    """Configuration for OpenAI Responses API format."""

    type: Literal[ProviderApiFormatType.OPENAI_RESPONSES] = ProviderApiFormatType.OPENAI_RESPONSES
