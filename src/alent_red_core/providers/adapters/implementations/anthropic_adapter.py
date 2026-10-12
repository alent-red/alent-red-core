from typing import AsyncIterator, Literal
import json
import base64
from uuid import uuid4
from anthropic import AsyncAnthropic, APIError, APIStatusError, APITimeoutError, RateLimitError
from anthropic._types import Omit
from anthropic.types import (
    Usage,
    MessageParam,
    TextBlock,
    ToolUseBlock,
    ToolResultBlockParam,
    ImageBlockParam,
    TextBlockParam,
    ThinkingConfigEnabledParam,
    CacheControlEphemeralParam,
    ToolParam,
)
from ....common import AttachedFilePathsPrompt, Logger
from ....models import (
    LlmResponse,
    LlmStreamItem,
    LlmUsage,
    MessageContent,
    MessageContentAi,
    MessageContentTool,
    MessageContentType,
    Error,
    ErrorCode,
    LlmModelImageDetail,
    LlmModelCache,
    AgentReasoning,
    AgentVerbosity,
    ProviderApiFormatAnthropic,
    ProviderApiFormatAnthropicCacheTtl,
    Blob,
    Tool,
)
from ..base_adapter import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    """Anthropic Messages API adapter."""

    def __init__(
        self,
        api_format: ProviderApiFormatAnthropic,
        base_url: str,
        api_key: str | None,
    ):
        """Initialize Anthropic adapter.

        Args:
            api_format: Anthropic API format configuration.
            base_url: Base URL for Anthropic API.
            api_key: Anthropic API key or None.
        """
        super().__init__(api_format, base_url, api_key)
        self._api_format: ProviderApiFormatAnthropic = api_format
        self._client = AsyncAnthropic(api_key=api_key, base_url=base_url)
        # Without a key (LM Studio, local servers) the SDK refuses to send a request
        # unless the auth header is explicitly omitted; an empty key would be refused too.
        self._request_headers: dict[str, Omit] | None = (
            {"X-Api-Key": Omit()} if api_key is None else None
        )
        self._logger = Logger.get_logger("providers.adapters.implementations.anthropic_adapter")

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
        """Generate AI response using Anthropic Messages API.

        Args:
            system_prompt: System instruction for the AI or None.
            messages: Conversation history.
            image_blobs: Dictionary mapping image file keys to Blob objects.
            tools: List of available tools.
            model_id: Model identifier.
            max_output_tokens_count: Maximum output tokens count to generate.
            top_p: Nucleus sampling parameter.
            image_detail: Image detail level (unused for Anthropic).
            cache: Cache duration for LLM responses.
            reasoning: Reasoning depth for agent processing.
            verbosity: Verbosity level for agent responses.
            attached_file_paths_prefix: Prefix for attached file paths.
            attached_file_paths_separator: Separator for attached file paths.
            no_tool_response_tag: Tag for tools with no response.

        Returns:
            List of MessageContent containing the AI response(s).

        Raises:
            Error: On API errors with appropriate error code.
        """
        self._logger.debug(
            "llm_started",
            model_id=model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            has_system_prompt=system_prompt is not None,
        )

        anthropic_messages = await self._build_anthropic_messages(
            messages,
            attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator,
            no_tool_response_prompt,
            cache,
            image_blobs,
        )

        thinking_config = self._build_thinking_config(reasoning)
        tools_param = self._build_tools_param(tools)

        try:
            # The SDK refuses a non-streaming request whose max_tokens could exceed its
            # 10-minute window, so the final message is collected through a stream.
            async with self._client.messages.stream(
                model=model_id,
                system=system_prompt if system_prompt is not None else Omit(),
                messages=anthropic_messages,
                max_tokens=max_output_tokens_count,
                # Sonnet 5 rejects sampling params (top_p/temperature/top_k) with a 400 when
                # set to non-default values. Disabled until adaptive-thinking support lands.
                thinking=thinking_config,
                tools=tools_param,
                extra_headers=self._request_headers,
            ) as stream:
                response = await stream.get_final_message()

            if not response.content:
                raise Error(ErrorCode.INVALID_RESPONSE, "Empty response content")

            result: list[MessageContent] = []
            turn_id = str(uuid4())

            for block in response.content:
                if block.type == "text":
                    result.append(
                        MessageContentAi(
                            type=MessageContentType.AI, text=block.text, processing=False
                        )
                    )

                elif block.type == "tool_use":
                    result.append(
                        MessageContentTool(
                            type=MessageContentType.TOOL,
                            name=block.name,
                            processing=False,
                            error=None,
                            request=json.dumps(block.input),
                            response=None,
                            llm_id=block.id,
                            turn_id=turn_id,
                        )
                    )

            self._logger.debug("llm_completed", response_content_count=len(result))

            return LlmResponse(contents=result, usage=self._build_usage(response.usage))

        except RateLimitError as e:
            raise Error(ErrorCode.RATE_LIMIT, f"Rate limit exceeded: {e.message}")
        except APITimeoutError as e:
            raise Error(ErrorCode.TIMEOUT, f"Request timeout: {e.message}")
        except APIStatusError as e:
            if e.status_code == 401 or e.status_code == 403:
                raise Error(ErrorCode.NOT_ALLOWED, f"Authentication failed: {e.message}")
            elif e.status_code == 400:
                raise Error(ErrorCode.INVALID_ARGUMENT, f"Invalid request: {e.message}")
            else:
                raise Error(ErrorCode.UNKNOWN, f"API error: {e.message}")
        except APIError as e:
            raise Error(ErrorCode.INVALID_RESPONSE, f"Invalid API response: {e.message}")
        except Exception as e:
            raise Error(ErrorCode.UNKNOWN, f"Unexpected error: {str(e)}")

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
        attached_file_path_prompt_prefix: str,
        attached_file_path_prompt_separator: str,
        no_tool_response_prompt: str,
    ) -> AsyncIterator[LlmStreamItem]:
        """Stream AI response using Anthropic Messages API.

        Args:
            system_prompt: System instruction for the AI.
            messages: Conversation history.
            image_blobs: Dictionary mapping image file keys to Blob objects.
            tools: List of available tools.
            model_id: Model identifier.
            max_output_tokens_count: Maximum output tokens count to generate.
            top_p: Nucleus sampling parameter.
            image_detail: Image detail level (unused for Anthropic).
            cache: Cache duration for LLM responses.
            reasoning: Reasoning depth for agent processing.
            verbosity: Verbosity level for agent responses.
            attached_file_paths_prefix: Prefix for attached file paths.
            attached_file_paths_separator: Separator for attached file paths.
            no_tool_response_tag: Tag for tools with no response.
            image_blobs: Dictionary mapping image file keys to Blob objects.

        Yields:
            MessageContent chunks as they arrive.

        Raises:
            Error: On API errors with appropriate error code.
        """

        self._logger.debug(
            "llm_stream_started",
            model_id=model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            has_system_prompt=system_prompt is not None,
        )

        anthropic_messages = await self._build_anthropic_messages(
            messages,
            attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator,
            no_tool_response_prompt,
            cache,
            image_blobs,
        )

        thinking_config = self._build_thinking_config(reasoning)
        tools_param = self._build_tools_param(tools)

        try:
            turn_id = str(uuid4())
            tool_states: dict[int, dict[str, str]] = {}
            chunk_count = 0

            async with self._client.messages.stream(
                model=model_id,
                system=system_prompt if system_prompt is not None else Omit(),
                messages=anthropic_messages,
                max_tokens=max_output_tokens_count,
                # Sonnet 5 rejects sampling params (top_p/temperature/top_k) with a 400 when
                # set to non-default values. Disabled until adaptive-thinking support lands.
                thinking=thinking_config,
                tools=tools_param,
                extra_headers=self._request_headers,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            tool_states[event.index] = {
                                "id": event.content_block.id,
                                "name": event.content_block.name,
                            }

                            yield MessageContentTool(
                                type=MessageContentType.TOOL,
                                name=tool_states[event.index]["name"],
                                processing=False,
                                error=None,
                                request="",
                                response=None,
                                llm_id=tool_states[event.index]["id"],
                                turn_id=turn_id,
                            )

                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            if event.delta.text:
                                chunk_count += 1
                                yield MessageContentAi(
                                    type=MessageContentType.AI,
                                    text=event.delta.text,
                                    processing=False,
                                )

                        elif event.delta.type == "input_json_delta":
                            if event.index in tool_states:
                                chunk_count += 1
                                if event.delta.partial_json:
                                    yield MessageContentTool(
                                        type=MessageContentType.TOOL,
                                        name=tool_states[event.index]["name"],
                                        processing=False,
                                        error=None,
                                        request=event.delta.partial_json,
                                        response=None,
                                        llm_id=tool_states[event.index]["id"],
                                        turn_id=turn_id,
                                    )

                final_message = await stream.get_final_message()

            yield self._build_usage(final_message.usage)

            self._logger.debug("llm_stream_completed", chunk_count=chunk_count)

        except RateLimitError as e:
            raise Error(ErrorCode.RATE_LIMIT, f"Rate limit exceeded: {e.message}")
        except APITimeoutError as e:
            raise Error(ErrorCode.TIMEOUT, f"Request timeout: {e.message}")
        except APIStatusError as e:
            if e.status_code == 401 or e.status_code == 403:
                raise Error(ErrorCode.NOT_ALLOWED, f"Authentication failed: {e.message}")
            elif e.status_code == 400:
                raise Error(ErrorCode.INVALID_ARGUMENT, f"Invalid request: {e.message}")
            else:
                raise Error(ErrorCode.UNKNOWN, f"API error: {e.message}")
        except APIError as e:
            raise Error(ErrorCode.INVALID_RESPONSE, f"Invalid API response: {e.message}")
        except Exception as e:
            raise Error(ErrorCode.UNKNOWN, f"Unexpected error: {str(e)}")

    async def _build_anthropic_messages(
        self,
        messages: list[MessageContent],
        attached_file_path_prompt_prefix: str,
        attached_file_path_prompt_separator: str,
        no_tool_response_prompt: str,
        cache: LlmModelCache,
        image_blobs: dict[str, Blob],
    ) -> list[MessageParam]:
        """Build Anthropic MessageParam list from MessageContent list.

        Args:
            messages: Internal message list.
            attached_file_path_prompt_prefix: Prefix added before attached file paths in the prompt.
            attached_file_path_prompt_separator: Separator between attached file paths in the prompt.
            no_tool_response_prompt: Prompt text for tools with no response.
            cache: Cache duration for LLM responses.
            image_blobs: Dictionary mapping image file keys to Blob objects.

        Returns:
            List of Anthropic MessageParam.
        """
        anthropic_messages: list[MessageParam] = []
        pending_tool_results: list[ToolResultBlockParam] = []
        current_turn_id: str | None = None

        for message in messages:
            if message.type == MessageContentType.AI:
                # Flash pending tool results
                if pending_tool_results:
                    anthropic_messages.append(
                        MessageParam(role="user", content=pending_tool_results.copy())
                    )
                    pending_tool_results.clear()

                anthropic_messages.append(
                    MessageParam(
                        role="assistant", content=[TextBlock(type="text", text=message.text)]
                    )
                )
                current_turn_id = None

            elif message.type == MessageContentType.TOOL:
                # Check if we can reuse last assistant message
                can_reuse = (
                    anthropic_messages
                    and anthropic_messages[-1]["role"] == "assistant"
                    and (current_turn_id == message.turn_id or current_turn_id is None)
                )

                if can_reuse:
                    # Reuse existing assistant - append tool_use to it
                    current_content = anthropic_messages[-1]["content"]
                    if isinstance(current_content, list):
                        current_content.append(
                            ToolUseBlock(
                                type="tool_use",
                                id=message.llm_id,
                                name=message.name,
                                input=json.loads(message.request),
                            )
                        )
                    else:
                        raise Error(
                            ErrorCode.INTERNAL,
                            "Expected assistant message content to be a list",
                        )
                else:
                    # Flash pending tool results
                    if pending_tool_results:
                        anthropic_messages.append(
                            MessageParam(role="user", content=pending_tool_results.copy())
                        )
                        pending_tool_results.clear()

                    # Create new assistant
                    tool_content: list[TextBlock | ToolUseBlock] = [
                        ToolUseBlock(
                            type="tool_use",
                            id=message.llm_id,
                            name=message.name,
                            input=json.loads(message.request),
                        )
                    ]
                    anthropic_messages.append(MessageParam(role="assistant", content=tool_content))

                # Build tool result content with text and optional images
                tool_result_content: list[TextBlockParam | ImageBlockParam] | str
                if message.response and (message.response.text or message.response.image_file_keys):
                    tool_result_content = []

                    # Add text if present
                    if message.response.text:
                        tool_result_content.append(
                            TextBlockParam(type="text", text=message.response.text)
                        )

                    # Add images if present
                    for file_key in message.response.image_file_keys:
                        blob_data = image_blobs.get(file_key)
                        if blob_data is None:
                            raise Error(
                                ErrorCode.INVALID_ARGUMENT,
                                f"Image blob not found for key: {file_key}",
                            )

                        tool_result_content.append(
                            ImageBlockParam(
                                type="image",
                                source={
                                    "type": "base64",
                                    "media_type": self._validate_image_media_type(
                                        blob_data.content_type
                                    ),
                                    "data": base64.b64encode(blob_data.content).decode("utf-8"),
                                },
                            )
                        )
                else:
                    tool_result_content = (
                        message.error if message.error else no_tool_response_prompt
                    )

                pending_tool_results.append(
                    ToolResultBlockParam(
                        type="tool_result",
                        tool_use_id=message.llm_id,
                        content=tool_result_content,
                    )
                )

                # Update turn tracking
                current_turn_id = message.turn_id

            elif (
                message.type == MessageContentType.USER
                or message.type == MessageContentType.INTERNAL
            ):
                if pending_tool_results:
                    anthropic_messages.append(
                        MessageParam(role="user", content=pending_tool_results.copy())
                    )
                    pending_tool_results.clear()

                message_text = message.text
                if message.type == MessageContentType.USER:
                    message_text = (
                        AttachedFilePathsPrompt.render(
                            text=message.text,
                            attached_file_paths=message.attached_file_paths,
                            prefix=attached_file_path_prompt_prefix,
                            separator=attached_file_path_prompt_separator,
                        )
                        or message.text
                    )

                anthropic_messages.append(MessageParam(role="user", content=message_text))
                current_turn_id = None

        # Flush any remaining pending tool results
        if pending_tool_results:
            anthropic_messages.append(
                MessageParam(role="user", content=pending_tool_results.copy())
            )
            pending_tool_results.clear()

        # Add cache_control to the last message if cache is enabled
        self._add_cache_to_last_message(anthropic_messages, cache)

        return anthropic_messages

    def _validate_image_media_type(
        self, media_type: str
    ) -> Literal["image/jpeg", "image/png", "image/gif", "image/webp"]:
        """Validate and return image media type.

        Args:
            media_type: Media type string to validate.

        Returns:
            Validated media type as Literal.

        Raises:
            Error: If media type is not supported.
        """
        if media_type == "image/jpeg":
            return "image/jpeg"
        elif media_type == "image/png":
            return "image/png"
        elif media_type == "image/gif":
            return "image/gif"
        elif media_type == "image/webp":
            return "image/webp"
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported image type: {media_type}")

    def _build_usage(self, usage: Usage) -> LlmUsage:
        # Anthropic reports prompt-cache reads and writes apart from input_tokens, so the
        # whole prompt is the sum of the three; LM Studio already counts them inside.
        input_tokens_count = usage.input_tokens
        if not self._api_format.input_tokens_include_cache:
            input_tokens_count += (usage.cache_creation_input_tokens or 0) + (
                usage.cache_read_input_tokens or 0
            )
        return LlmUsage(
            input_tokens_count=input_tokens_count, output_tokens_count=usage.output_tokens
        )

    def _build_thinking_config(
        self, reasoning: AgentReasoning
    ) -> ThinkingConfigEnabledParam | Omit:
        """Build thinking configuration for extended thinking.

        Args:
            reasoning: Reasoning depth for agent processing.

        Returns:
            Thinking config or Omit if reasoning is DEFAULT.
        """
        if reasoning == AgentReasoning.DEFAULT:
            return Omit()

        budget_tokens_map = {
            AgentReasoning.MINIMAL: self._api_format.reasoning_minimal_budget_tokens,
            AgentReasoning.LOW: self._api_format.reasoning_low_budget_tokens,
            AgentReasoning.MEDIUM: self._api_format.reasoning_medium_budget_tokens,
            AgentReasoning.HIGH: self._api_format.reasoning_high_budget_tokens,
            AgentReasoning.XHIGH: self._api_format.reasoning_xhigh_budget_tokens,
        }

        budget_tokens = budget_tokens_map[reasoning]

        return ThinkingConfigEnabledParam(type="enabled", budget_tokens=budget_tokens)

    def _build_tools_param(self, tools: list[Tool] | None) -> list[ToolParam] | Omit:
        """Build tools parameter for Anthropic API.

        Args:
            tools: List of available tools.

        Returns:
            List of Anthropic ToolParam or Omit if no tools.
        """
        if not tools:
            return Omit()

        anthropic_tools: list[ToolParam] = []
        for tool in tools:
            anthropic_tools.append(
                ToolParam(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.parameters_schema,
                )
            )

        return anthropic_tools

    def _add_cache_to_last_message(
        self, anthropic_messages: list[MessageParam], cache: LlmModelCache
    ) -> None:
        """Add cache_control to the last content block of the last message.

        Args:
            anthropic_messages: List of Anthropic messages to modify.
            cache: Cache duration for LLM responses.
        """
        if not anthropic_messages or cache == LlmModelCache.DEFAULT:
            return

        if cache == LlmModelCache.MEDIUM:
            cache_ttl_enum = self._api_format.cache_medium_ttl
        elif cache == LlmModelCache.HIGH:
            cache_ttl_enum = self._api_format.cache_high_ttl
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported cache level: {cache}")

        if cache_ttl_enum == ProviderApiFormatAnthropicCacheTtl.DEFAULT:
            return

        cache_ttl: Literal["5m", "1h"] = cache_ttl_enum.value
        last_message = anthropic_messages[-1]
        content = last_message.get("content")

        if isinstance(content, list) and content:
            last_content_block = content[-1]
            if isinstance(last_content_block, dict):
                last_content_block["cache_control"] = CacheControlEphemeralParam(
                    type="ephemeral", ttl=cache_ttl
                )
