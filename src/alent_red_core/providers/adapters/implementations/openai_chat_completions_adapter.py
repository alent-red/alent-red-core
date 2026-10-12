from typing import AsyncIterator, Literal
import base64
from uuid import uuid4
from openai import AsyncOpenAI, APIError, APIStatusError, APITimeoutError, RateLimitError
from openai._types import Omit
from openai.types import CompletionUsage
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionUserMessageParam,
    ChatCompletionAssistantMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionContentPartImageParam,
    ChatCompletionToolParam,
)
from openai.types.chat.chat_completion_message_tool_call_param import (
    ChatCompletionMessageToolCallParam,
    Function,
)
from ....common import AttachedFilePathsPrompt, Logger
from ....models import (
    LlmResponse,
    LlmStreamItem,
    LlmUsage,
    MessageContent,
    MessageContentAi,
    MessageContentType,
    MessageContentTool,
    Error,
    ErrorCode,
    LlmModelImageDetail,
    LlmModelCache,
    AgentReasoning,
    AgentVerbosity,
    ProviderApiFormatOpenAiChatCompletions,
    Blob,
    Tool,
)
from ..base_adapter import BaseAdapter


class OpenAiChatCompletionsAdapter(BaseAdapter):
    """OpenAI Chat Completions API adapter."""

    def __init__(
        self,
        api_format: ProviderApiFormatOpenAiChatCompletions,
        base_url: str,
        api_key: str | None,
    ):
        """Initialize OpenAI Chat Completions adapter.

        Args:
            api_format: OpenAI Chat Completions API format configuration.
            base_url: Base URL for OpenAI API.
            api_key: OpenAI API key or None.
        """
        super().__init__(api_format, base_url, api_key)
        self._api_format: ProviderApiFormatOpenAiChatCompletions = api_format
        self._client = AsyncOpenAI(api_key=api_key or "", base_url=base_url)
        self._logger = Logger.get_logger(
            "providers.adapters.implementations.openai_chat_completions_adapter"
        )

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
        """Generate AI response using OpenAI Chat Completions API.

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
            List of MessageContent containing the AI response(s).

        Raises:
            Error: On API errors with appropriate error code.
        """
        openai_messages = await self._build_openai_messages(
            system_prompt,
            messages,
            attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator,
            no_tool_response_prompt,
            image_detail,
            image_blobs,
        )

        self._logger.debug(
            "llm_started",
            model_id=model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            has_system_prompt=system_prompt is not None,
        )

        reasoning_effort = self._build_reasoning_effort(reasoning)
        tools_param = self._build_tools_param(tools)

        try:
            response = await self._client.chat.completions.create(
                model=model_id,
                messages=openai_messages,
                max_completion_tokens=max_output_tokens_count,
                # top_p=top_p,
                reasoning_effort=reasoning_effort,
                tools=tools_param,
            )

            if not response.choices:
                raise Error(ErrorCode.INVALID_RESPONSE, "Empty response choices")

            message = response.choices[0].message
            result: list[MessageContent] = []
            turn_id = str(uuid4())

            if message.content is not None:
                result.append(
                    MessageContentAi(
                        type=MessageContentType.AI, text=message.content, processing=False
                    )
                )

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.type == "function" and hasattr(tool_call, "function"):
                        result.append(
                            MessageContentTool(
                                type=MessageContentType.TOOL,
                                name=tool_call.function.name,
                                processing=False,
                                error=None,
                                request=tool_call.function.arguments,
                                response=None,
                                llm_id=tool_call.id,
                                turn_id=turn_id,
                            )
                        )

            if not result:
                raise Error(ErrorCode.INVALID_RESPONSE, "Response has no content or tool calls")

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
        """Stream AI response using OpenAI Chat Completions API.

        Args:
            system_prompt: System instruction for the AI.
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

        openai_messages = await self._build_openai_messages(
            system_prompt,
            messages,
            attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator,
            no_tool_response_prompt,
            image_detail,
            image_blobs,
        )

        turn_id = str(uuid4())
        tool_states: dict[int, dict[str, str]] = {}
        reasoning_effort = self._build_reasoning_effort(reasoning)
        tools_param = self._build_tools_param(tools)
        chunk_count = 0

        try:
            stream = await self._client.chat.completions.create(
                model=model_id,
                messages=openai_messages,
                max_completion_tokens=max_output_tokens_count,
                # top_p=top_p,
                reasoning_effort=reasoning_effort,
                tools=tools_param,
                stream=True,
                stream_options={"include_usage": True},
            )

            usage: CompletionUsage | None = None
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if chunk.choices and chunk.choices:
                    delta = chunk.choices[0].delta

                    if delta.content:
                        chunk_count += 1
                        yield MessageContentAi(
                            type=MessageContentType.AI, text=delta.content, processing=False
                        )

                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            if tool_call.index not in tool_states:
                                func_name = ""
                                if tool_call.function and tool_call.function.name:
                                    func_name = tool_call.function.name
                                tool_states[tool_call.index] = {
                                    "id": tool_call.id or "",
                                    "name": func_name,
                                }

                                yield MessageContentTool(
                                    type=MessageContentType.TOOL,
                                    name=tool_states[tool_call.index]["name"],
                                    processing=False,
                                    error=None,
                                    request="",
                                    response=None,
                                    llm_id=tool_states[tool_call.index]["id"],
                                    turn_id=turn_id,
                                )

                            if tool_call.id:
                                tool_states[tool_call.index]["id"] = tool_call.id
                            if tool_call.function and tool_call.function.name:
                                tool_states[tool_call.index]["name"] = tool_call.function.name

                            if tool_call.function and tool_call.function.arguments:
                                chunk_count += 1
                                yield MessageContentTool(
                                    type=MessageContentType.TOOL,
                                    name=tool_states[tool_call.index]["name"],
                                    processing=False,
                                    error=None,
                                    request=tool_call.function.arguments,
                                    response=None,
                                    llm_id=tool_states[tool_call.index]["id"],
                                    turn_id=turn_id,
                                )

            if usage is None:
                raise Error(
                    ErrorCode.INVALID_RESPONSE, "Chat completion stream ended without usage"
                )
            yield self._build_usage(usage)

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

    def _build_usage(self, usage: CompletionUsage | None) -> LlmUsage:
        if usage is None:
            raise Error(ErrorCode.INVALID_RESPONSE, "Chat completion response has no usage")
        return LlmUsage(
            input_tokens_count=usage.prompt_tokens, output_tokens_count=usage.completion_tokens
        )

    def _build_reasoning_effort(
        self, reasoning: AgentReasoning
    ) -> Literal["none", "minimal", "low", "medium", "high", "xhigh"] | Omit:
        """Build reasoning_effort parameter for OpenAI API.

        Args:
            reasoning: Internal reasoning level enum.

        Returns:
            OpenAI reasoning_effort value or Omit if DEFAULT.
        """
        if reasoning == AgentReasoning.DEFAULT:
            return Omit()

        reasoning_effort_map: dict[
            AgentReasoning, Literal["none", "minimal", "low", "medium", "high", "xhigh"]
        ] = {
            AgentReasoning.MINIMAL: "minimal",
            AgentReasoning.LOW: "low",
            AgentReasoning.MEDIUM: "medium",
            AgentReasoning.HIGH: "high",
            AgentReasoning.XHIGH: "xhigh",
        }

        return reasoning_effort_map[reasoning]

    def _build_tools_param(self, tools: list[Tool] | None) -> list[ChatCompletionToolParam] | Omit:
        """Build tools parameter for OpenAI Chat Completions API.

        Args:
            tools: List of Tool definitions.

        Returns:
            List of ChatCompletionToolParam or Omit if no tools.
        """
        if not tools:
            return Omit()

        openai_tools: list[ChatCompletionToolParam] = []
        for tool in tools:
            openai_tools.append(
                ChatCompletionToolParam(
                    type="function",
                    function={
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema,
                    },
                )
            )

        return openai_tools

    def _map_image_detail(
        self, image_detail: LlmModelImageDetail
    ) -> Literal["auto", "low", "high"]:
        """Map LlmModelImageDetail to OpenAI's expected detail values.

        Args:
            image_detail: Internal image detail enum.

        Returns:
            OpenAI image detail value.
        """
        if image_detail == LlmModelImageDetail.DEFAULT:
            return "auto"
        elif image_detail == LlmModelImageDetail.LOW:
            return "low"
        elif image_detail == LlmModelImageDetail.HIGH:
            return "high"
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unknown image detail: {image_detail}")

    async def _build_openai_messages(
        self,
        system_prompt: str | None,
        messages: list[MessageContent],
        attached_file_path_prompt_prefix: str,
        attached_file_path_prompt_separator: str,
        no_tool_response_prompt: str,
        image_detail: LlmModelImageDetail,
        image_blobs: dict[str, Blob],
    ) -> list[ChatCompletionMessageParam]:
        """Build OpenAI ChatCompletionMessageParam list from MessageContent list.

        Args:
            system_prompt: System instruction for the AI or None.
            messages: Internal message list.
            attached_file_path_prompt_prefix: Prefix added before attached file paths in the prompt.
            attached_file_path_prompt_separator: Separator between attached file paths in the prompt.
            no_tool_response_prompt: Prompt text for tools with no response.
            image_detail: Image detail level for vision capabilities.
            image_blobs: Dictionary mapping image file keys to Blob objects.

        Returns:
            List of OpenAI ChatCompletionMessageParam.
        """
        openai_messages: list[ChatCompletionMessageParam] = []
        if system_prompt is not None:
            openai_messages.append({"role": "system", "content": system_prompt})

        pending_tool_responses: list[ChatCompletionToolMessageParam] = []
        pending_user_message_for_images: ChatCompletionUserMessageParam | None = None
        current_turn_id: str | None = None

        for message in messages:
            if message.type == MessageContentType.AI:
                # Flush pending tool responses and images
                if pending_tool_responses:
                    openai_messages.extend(pending_tool_responses.copy())
                    pending_tool_responses.clear()

                if pending_user_message_for_images:
                    openai_messages.append(pending_user_message_for_images)
                    pending_user_message_for_images = None

                openai_messages.append(
                    ChatCompletionAssistantMessageParam(role="assistant", content=message.text)
                )
                current_turn_id = None

            elif message.type == MessageContentType.TOOL:
                # Check if we can reuse last assistant message
                can_reuse = (
                    openai_messages
                    and openai_messages[-1]["role"] == "assistant"
                    and (current_turn_id == message.turn_id or current_turn_id is None)
                )

                if can_reuse:
                    # Reuse existing assistant - add tool_calls if not present
                    last_message = openai_messages[-1]
                    if last_message["role"] == "assistant":
                        if "tool_calls" not in last_message:
                            last_message["tool_calls"] = []

                        if isinstance(last_message["tool_calls"], list):
                            last_message["tool_calls"].append(
                                ChatCompletionMessageToolCallParam(
                                    id=message.llm_id,
                                    type="function",
                                    function=Function(
                                        name=message.name,
                                        arguments=message.request,
                                    ),
                                )
                            )
                else:
                    # Flush pending before creating new assistant
                    if pending_tool_responses:
                        openai_messages.extend(pending_tool_responses.copy())
                        pending_tool_responses.clear()

                    if pending_user_message_for_images:
                        openai_messages.append(pending_user_message_for_images)
                        pending_user_message_for_images = None

                    # Create new assistant with tool_calls
                    openai_messages.append(
                        ChatCompletionAssistantMessageParam(
                            role="assistant",
                            tool_calls=[
                                ChatCompletionMessageToolCallParam(
                                    id=message.llm_id,
                                    type="function",
                                    function=Function(
                                        name=message.name,
                                        arguments=message.request,
                                    ),
                                )
                            ],
                        )
                    )

                # Queue tool response (text only)
                response_text = (
                    message.response.text
                    if message.response and message.response.text
                    else (message.error if message.error else no_tool_response_prompt)
                )

                pending_tool_responses.append(
                    ChatCompletionToolMessageParam(
                        role="tool",
                        tool_call_id=message.llm_id,
                        content=response_text,
                    )
                )

                # Handle images from tool response
                if message.response and message.response.image_file_keys:
                    # Create user message for images if not exists
                    if pending_user_message_for_images is None:
                        pending_user_message_for_images = ChatCompletionUserMessageParam(
                            role="user", content=[]
                        )

                    # Add images to user message
                    content_list = pending_user_message_for_images["content"]
                    if isinstance(content_list, list):
                        for file_key in message.response.image_file_keys:
                            blob_data = image_blobs.get(file_key)
                            if blob_data is None:
                                raise Error(
                                    ErrorCode.INVALID_ARGUMENT,
                                    f"Image blob not found for key: {file_key}",
                                )
                            content_list.append(
                                ChatCompletionContentPartImageParam(
                                    type="image_url",
                                    image_url={
                                        "url": f"data:{blob_data.content_type};base64,{base64.b64encode(blob_data.content).decode('utf-8')}",
                                        "detail": self._map_image_detail(image_detail),
                                    },
                                )
                            )

                # Update turn tracking
                current_turn_id = message.turn_id

            elif (
                message.type == MessageContentType.USER
                or message.type == MessageContentType.INTERNAL
            ):
                # Flush pending tool responses and images
                if pending_tool_responses:
                    openai_messages.extend(pending_tool_responses.copy())
                    pending_tool_responses.clear()

                if pending_user_message_for_images:
                    openai_messages.append(pending_user_message_for_images)
                    pending_user_message_for_images = None

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

                openai_messages.append(
                    ChatCompletionUserMessageParam(role="user", content=message_text)
                )
                current_turn_id = None

        # Flush any remaining pending tool responses and images
        if pending_tool_responses:
            openai_messages.extend(pending_tool_responses.copy())
            pending_tool_responses.clear()

        if pending_user_message_for_images:
            openai_messages.append(pending_user_message_for_images)
            pending_user_message_for_images = None

        return openai_messages
