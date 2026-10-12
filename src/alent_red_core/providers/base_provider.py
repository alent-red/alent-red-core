from typing import AsyncIterator

from ..models import (
    AgentReasoning,
    AgentVerbosity,
    Blob,
    Error,
    ErrorCode,
    LlmModelCache,
    LlmModelImageDetail,
    LlmResponse,
    LlmStreamItem,
    MessageContent,
    PreferenceKey,
    PreferenceValueType,
    ProviderConfig,
    Tool,
)
from ..database import Database


class BaseProvider:
    """Base class for all providers.

    Providers are global instances initialized once and used across conversations.
    """

    def __init__(self, config: ProviderConfig, database: Database):
        """Initialize provider.

        Args:
            config: Provider configuration.
            database: Database instance.
        """
        self._config = config
        self._database = database
        self._attached_file_path_prompt_prefix: str = ""
        self._attached_file_path_prompt_separator: str = ""
        self._no_tool_response_prompt: str = ""

    async def setup(self) -> None:
        """Setup provider resources. Override in subclasses if needed.

        Raises:
            Error: If required preferences are not found.
        """
        await self._load_preferences()

    async def refresh(self, config: ProviderConfig) -> None:
        """Refresh provider resources. Override in subclasses if needed.

        Args:
            config: Updated provider configuration.

        Raises:
            Error: If required preferences are not found.
        """
        self._config = config
        await self._load_preferences()

    async def clean(self) -> None:
        """Clean provider resources. Override in subclasses if needed."""
        pass

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
    ) -> LlmResponse:
        """Generate LLM response without streaming.

        Args:
            system_prompt: System prompt or None.
            messages: List of message content.
            image_blobs: Dictionary mapping image keys to Blob objects.
            tools: List of available tools.
            model_id: Model identifier string.
            max_output_tokens_count: Maximum output tokens count for response.
            top_p: Top p sampling parameter.
            image_detail: Image detail level.
            cache: Cache configuration.
            reasoning: Agent reasoning mode.
            verbosity: Agent verbosity level.

        Returns:
            The contents produced and the usage of the call.

        Raises:
            Error: If provider does not support non-streaming LLM.
        """
        raise Error(ErrorCode.NOT_SUPPORTED, "Provider does not support non-streaming LLM")

    async def llm_stream(
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
    ) -> AsyncIterator[LlmStreamItem]:
        """Generate LLM response with streaming.

        Args:
            system_prompt: System prompt or None.
            messages: List of message content.
            image_blobs: Dictionary mapping image keys to Blob objects.
            tools: List of available tools.
            model_id: Model identifier string.
            max_output_tokens_count: Maximum output tokens count for response.
            top_p: Top p sampling parameter.
            image_detail: Image detail level.
            cache: Cache configuration.
            reasoning: Agent reasoning mode.
            verbosity: Agent verbosity level.

        Yields:
            Message content chunks from LLM, then the usage of the call.

        Raises:
            Error: If provider does not support streaming LLM.
        """
        if False:
            yield  # Make it an async generator
        raise Error(ErrorCode.NOT_SUPPORTED, "Provider does not support streaming LLM")

    async def _load_preferences(self) -> None:
        """Load required preferences from database.

        Raises:
            Error: If required preferences are not found or have invalid types.
        """
        attached_file_path_prompt_prefix_preference = await self._database.preferences.get(
            PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX
        )
        if attached_file_path_prompt_prefix_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX} not found",
            )
        if attached_file_path_prompt_prefix_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX} must be string type",
            )

        attached_file_path_prompt_separator_preference = await self._database.preferences.get(
            PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR
        )
        if attached_file_path_prompt_separator_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR} not found",
            )
        if attached_file_path_prompt_separator_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR} must be string type",
            )

        no_tool_response_prompt_preference = await self._database.preferences.get(
            PreferenceKey.NO_TOOL_RESPONSE_PROMPT
        )
        if no_tool_response_prompt_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.NO_TOOL_RESPONSE_PROMPT} not found",
            )
        if no_tool_response_prompt_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.NO_TOOL_RESPONSE_PROMPT} must be string type",
            )

        self._attached_file_path_prompt_prefix = (
            attached_file_path_prompt_prefix_preference.value.value
        )
        self._attached_file_path_prompt_separator = (
            attached_file_path_prompt_separator_preference.value.value
        )
        self._no_tool_response_prompt = no_tool_response_prompt_preference.value.value
