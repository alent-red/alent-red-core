from typing import AsyncIterator

from ...common import Logger
from ..base_provider import BaseProvider
from ...models import (
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
    ProviderApiFormatAnthropic,
    ProviderApiFormatAnthropicCacheTtl,
    ProviderApiFormatOpenAiChatCompletions,
    ProviderConfig,
    ProviderConfigType,
    Tool,
)
from ...database import Database
from ..adapters import AdapterBuilder, BaseAdapter


class CommonProvider(BaseProvider):
    """Common provider for all API formats (Anthropic, OpenAI Chat Completions, OpenAI Responses)."""

    def __init__(self, config: ProviderConfig, database: Database):
        """Initialize common provider.

        Args:
            config: Provider configuration.
            database: Database instance.
        """
        super().__init__(config, database)
        self._adapter: BaseAdapter | None = None
        self._logger = Logger.get_logger("providers.implementations.common_provider")

    async def setup(self) -> None:
        """Setup provider resources.

        Raises:
            Error: If required preferences are not found or adapter cannot be built.
        """
        self._logger.debug("setup_started", config_type=self._config.type.value)

        await super().setup()
        await self._build_adapter(self._config)

        self._logger.debug("setup_completed", config_type=self._config.type.value)

    async def refresh(self, config: ProviderConfig) -> None:
        """Refresh provider resources.

        Args:
            config: Updated provider configuration.

        Raises:
            Error: If required preferences are not found or adapter cannot be built.
        """
        self._logger.debug("refresh_started", config_type=config.type.value)

        await super().refresh(config)
        await self._build_adapter(self._config)

        self._logger.debug("refresh_completed", config_type=self._config.type.value)

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
        """
        self._logger.debug(
            "llm_started",
            model_id=model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            image_count=len(image_blobs),
        )

        if self._adapter is None:
            raise Error(ErrorCode.INTERNAL, "Adapter not initialized")

        result = await self._adapter.llm(
            system_prompt=system_prompt,
            messages=messages,
            image_blobs=image_blobs,
            tools=tools,
            model_id=model_id,
            max_output_tokens_count=max_output_tokens_count,
            top_p=top_p,
            image_detail=image_detail,
            cache=cache,
            reasoning=reasoning,
            verbosity=verbosity,
            attached_file_path_prompt_prefix=self._attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator=self._attached_file_path_prompt_separator,
            no_tool_response_prompt=self._no_tool_response_prompt,
        )

        self._logger.debug("llm_completed", response_content_count=len(result.contents))

        return result

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
        """
        self._logger.debug(
            "llm_stream_started",
            model_id=model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            image_count=len(image_blobs),
        )

        if self._adapter is None:
            raise Error(ErrorCode.INTERNAL, "Adapter not initialized")

        chunk_count = 0
        async for content in self._adapter.llm_stream(
            system_prompt=system_prompt,
            messages=messages,
            image_blobs=image_blobs,
            tools=tools,
            model_id=model_id,
            max_output_tokens_count=max_output_tokens_count,
            top_p=top_p,
            image_detail=image_detail,
            cache=cache,
            reasoning=reasoning,
            verbosity=verbosity,
            attached_file_path_prompt_prefix=self._attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator=self._attached_file_path_prompt_separator,
            no_tool_response_prompt=self._no_tool_response_prompt,
        ):
            chunk_count += 1
            yield content

        self._logger.debug("llm_stream_completed", chunk_count=chunk_count)

    async def _build_adapter(self, config: ProviderConfig) -> None:
        """Build adapter based on provider configuration.

        Args:
            config: Provider configuration.

        Raises:
            Error: If required preferences are not found or configuration is invalid.
        """
        if config.type == ProviderConfigType.OPENAI:
            # Performance Note: OpenAI Responses API is the officially recommended format, but
            # extensive testing shows it consistently adds 30-100% latency compared to the legacy
            # ChatCompletions API. For optimal inference speed, we use ChatCompletions instead.
            base_url = await self._load_preference_string(PreferenceKey.OPEN_AI_BASE_URL)
            openai_api_format = ProviderApiFormatOpenAiChatCompletions()
            self._adapter = AdapterBuilder.build(openai_api_format, base_url, config.api_key)

        elif config.type == ProviderConfigType.ANTHROPIC:
            base_url = await self._load_preference_string(PreferenceKey.ANTHROPIC_BASE_URL)
            anthropic_api_format = await self._load_anthropic_api_format(
                input_tokens_include_cache=False
            )
            self._adapter = AdapterBuilder.build(anthropic_api_format, base_url, config.api_key)

        elif config.type == ProviderConfigType.LM_STUDIO:
            # LM Studio speaks the Anthropic format but counts cached tokens inside input_tokens.
            lm_studio_api_format = await self._load_anthropic_api_format(
                input_tokens_include_cache=True
            )
            self._adapter = AdapterBuilder.build(lm_studio_api_format, str(config.base_url), None)

        elif config.type == ProviderConfigType.CUSTOM:
            self._adapter = AdapterBuilder.build(
                config.api_format, str(config.base_url), config.api_key
            )

        else:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"Unsupported provider config type: {config.type}",
            )

    async def _load_anthropic_api_format(
        self, input_tokens_include_cache: bool
    ) -> ProviderApiFormatAnthropic:
        """Load Anthropic API format configuration from preferences.

        Args:
            input_tokens_include_cache: Whether the server counts prompt-cache tokens
                inside input_tokens (LM Studio) or apart from them (Anthropic).

        Returns:
            Configured ProviderApiFormatAnthropic instance.

        Raises:
            Error: If required preferences are not found or have invalid types.
        """
        reasoning_minimal_budget_tokens = await self._load_preference_int(
            PreferenceKey.ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS
        )
        reasoning_low_budget_tokens = await self._load_preference_int(
            PreferenceKey.ANTHROPIC_REASONING_LOW_BUDGET_TOKENS
        )
        reasoning_medium_budget_tokens = await self._load_preference_int(
            PreferenceKey.ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS
        )
        reasoning_high_budget_tokens = await self._load_preference_int(
            PreferenceKey.ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS
        )
        reasoning_xhigh_budget_tokens = await self._load_preference_int(
            PreferenceKey.ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS
        )
        cache_medium_ttl_value = await self._load_preference_string(
            PreferenceKey.ANTHROPIC_CACHE_MEDIUM_TTL
        )
        cache_high_ttl_value = await self._load_preference_string(
            PreferenceKey.ANTHROPIC_CACHE_HIGH_TTL
        )

        try:
            cache_medium_ttl = ProviderApiFormatAnthropicCacheTtl(cache_medium_ttl_value)
        except ValueError:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Invalid value for {PreferenceKey.ANTHROPIC_CACHE_MEDIUM_TTL}: {cache_medium_ttl_value}",
            )

        try:
            cache_high_ttl = ProviderApiFormatAnthropicCacheTtl(cache_high_ttl_value)
        except ValueError:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Invalid value for {PreferenceKey.ANTHROPIC_CACHE_HIGH_TTL}: {cache_high_ttl_value}",
            )

        return ProviderApiFormatAnthropic(
            reasoning_minimal_budget_tokens=reasoning_minimal_budget_tokens,
            reasoning_low_budget_tokens=reasoning_low_budget_tokens,
            reasoning_medium_budget_tokens=reasoning_medium_budget_tokens,
            reasoning_high_budget_tokens=reasoning_high_budget_tokens,
            reasoning_xhigh_budget_tokens=reasoning_xhigh_budget_tokens,
            cache_medium_ttl=cache_medium_ttl,
            cache_high_ttl=cache_high_ttl,
            input_tokens_include_cache=input_tokens_include_cache,
        )

    async def _load_preference_string(self, key: PreferenceKey) -> str:
        """Load string preference value.

        Args:
            key: Preference key to load.

        Returns:
            String preference value.

        Raises:
            Error: If preference not found or has invalid type.
        """
        preference = await self._database.preferences.get(key)
        if preference is None:
            raise Error(ErrorCode.NOT_FOUND, f"Required preference {key} not found")
        if preference.value.type != PreferenceValueType.STRING:
            raise Error(ErrorCode.INVALID_RESPONSE, f"Preference {key} must be string type")
        return preference.value.value

    async def _load_preference_int(self, key: PreferenceKey) -> int:
        """Load int preference value.

        Args:
            key: Preference key to load.

        Returns:
            Int preference value.

        Raises:
            Error: If preference not found or has invalid type.
        """
        preference = await self._database.preferences.get(key)
        if preference is None:
            raise Error(ErrorCode.NOT_FOUND, f"Required preference {key} not found")
        if preference.value.type != PreferenceValueType.INT:
            raise Error(ErrorCode.INVALID_RESPONSE, f"Preference {key} must be int type")
        return preference.value.value
