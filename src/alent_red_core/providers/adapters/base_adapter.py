from abc import ABC, abstractmethod
from typing import AsyncIterator
from ...models import (
    LlmResponse,
    LlmStreamItem,
    MessageContent,
    LlmModelImageDetail,
    LlmModelCache,
    AgentReasoning,
    AgentVerbosity,
    Blob,
    ProviderApiFormat,
    Tool,
)


class BaseAdapter(ABC):
    """Base adapter for LLM API integrations."""

    def __init__(
        self,
        api_format: ProviderApiFormat,
        base_url: str,
        api_key: str | None,
    ):
        """Initialize adapter with API credentials.

        Args:
            api_format: API format configuration.
            base_url: Base URL for API endpoint.
            api_key: API key for authentication or None.
        """
        self._api_format = api_format
        self._base_url = base_url
        self._api_key = api_key

    @abstractmethod
    async def llm(
        self,
        system_prompt: str | None,
        messages: list[MessageContent],
        image_blobs: dict[str, Blob],
        tools: list[Tool] | None,
        model_id: str,
        max_output_tokens_count: int,
        top_p: float,
        image_detail: LlmModelImageDetail,
        cache: LlmModelCache,
        reasoning: AgentReasoning,
        verbosity: AgentVerbosity,
        attached_file_path_prompt_prefix: str,
        attached_file_path_prompt_separator: str,
        no_tool_response_prompt: str,
    ) -> LlmResponse:
        """Generate AI response from conversation messages.

        Args:
            system_prompt: System instruction for the AI or None.
            messages: Conversation history.
            image_blobs: Dictionary mapping image file keys to Blob objects.
            tools: List of available tools.
            model_id: Model identifier.
            max_output_tokens_count: Maximum output tokens count to generate.
            top_p: Nucleus sampling parameter.
            image_detail: Image detail level for vision capabilities.
            cache: Cache duration for LLM responses.
            reasoning: Reasoning depth for agent processing.
            verbosity: Verbosity level for agent responses.
            attached_file_path_prompt_prefix: Prefix added before attached file paths in the prompt.
            attached_file_path_prompt_separator: Separator between attached file paths in the prompt.
            no_tool_response_prompt: Prompt text for tools with no response.

        Returns:
            The contents produced and the usage of the call.
        """
        pass

    @abstractmethod
    def llm_stream(
        self,
        system_prompt: str | None,
        messages: list[MessageContent],
        image_blobs: dict[str, Blob],
        tools: list[Tool] | None,
        model_id: str,
        max_output_tokens_count: int,
        top_p: float,
        image_detail: LlmModelImageDetail,
        cache: LlmModelCache,
        reasoning: AgentReasoning,
        verbosity: AgentVerbosity,
        attached_file_path_prompt_prefix: str,
        attached_file_path_prompt_separator: str,
        no_tool_response_prompt: str,
    ) -> AsyncIterator[LlmStreamItem]:
        """Stream AI response as incremental chunks.

        Args:
            system_prompt: System instruction for the AI or None.
            messages: Conversation history.
            image_blobs: Dictionary mapping image file keys to Blob objects.
            tools: List of available tools.
            model_id: Model identifier.
            max_output_tokens_count: Maximum output tokens count to generate.
            top_p: Nucleus sampling parameter.
            image_detail: Image detail level for vision capabilities.
            cache: Cache duration for LLM responses.
            reasoning: Reasoning depth for agent processing.
            verbosity: Verbosity level for agent responses.
            attached_file_path_prompt_prefix: Prefix added before attached file paths in the prompt.
            attached_file_path_prompt_separator: Separator between attached file paths in the prompt.
            no_tool_response_prompt: Prompt text for tools with no response.

        Yields:
            MessageContent chunks (deltas) as they arrive, then the LlmUsage of the call.
        """
        pass
