from ...models import (
    ProviderApiFormat,
    ProviderApiFormatType,
    Error,
    ErrorCode,
)
from .base_adapter import BaseAdapter
from .implementations import (
    AnthropicAdapter,
    OpenAiChatCompletionsAdapter,
    OpenAiResponsesAdapter,
)


class AdapterBuilder:
    """Factory for building LLM API adapters."""

    @staticmethod
    def build(
        api_format: ProviderApiFormat,
        base_url: str,
        api_key: str | None,
    ) -> BaseAdapter:
        """Build adapter for specified API format.

        Args:
            api_format: API format configuration.
            base_url: Base URL for API endpoint.
            api_key: API key for authentication or None.

        Returns:
            Configured adapter instance.

        Raises:
            Error: If API format is not supported.
        """
        if api_format.type == ProviderApiFormatType.ANTHROPIC:
            return AnthropicAdapter(api_format, base_url, api_key)
        elif api_format.type == ProviderApiFormatType.OPENAI_CHAT_COMPLETIONS:
            return OpenAiChatCompletionsAdapter(api_format, base_url, api_key)
        elif api_format.type == ProviderApiFormatType.OPENAI_RESPONSES:
            return OpenAiResponsesAdapter(api_format, base_url, api_key)
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported API format type: {api_format.type}")
