from typing import Literal

from pydantic import BaseModel

from .provider_api_format_type import ProviderApiFormatType


class ProviderApiFormatOpenAiChatCompletions(BaseModel):
    """Configuration for OpenAI Chat Completions API format."""

    type: Literal[ProviderApiFormatType.OPENAI_CHAT_COMPLETIONS] = (
        ProviderApiFormatType.OPENAI_CHAT_COMPLETIONS
    )
