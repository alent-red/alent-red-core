from typing import AsyncIterator, Literal
import base64
from uuid import uuid4
from openai import AsyncOpenAI, APIError, APIStatusError, APITimeoutError, RateLimitError
from openai._types import Omit
from openai.types.shared_params import Reasoning
from openai.types.responses import (
    ResponseUsage,
    ResponseInputParam,
    ResponseFunctionToolCallParam,
    ResponseInputTextParam,
    ResponseFunctionCallOutputItemListParam,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseOutputItemAddedEvent,
    ResponseTextDeltaEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    FunctionToolParam,
)
from openai.types.responses.response_input_text_content_param import (
    ResponseInputTextContentParam,
)
from openai.types.responses.response_input_image_content_param import (
    ResponseInputImageContentParam,
)
from openai.types.responses.response_output_message_param import ResponseOutputMessageParam
from openai.types.responses.response_output_text_param import ResponseOutputTextParam
from openai.types.responses.response_input_param import Message, FunctionCallOutput
from openai.types.responses.response_text_config_param import ResponseTextConfigParam
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
    ProviderApiFormatOpenAiResponses,
    Blob,
    Tool,
)
from ..base_adapter import BaseAdapter


class OpenAiResponsesAdapter(BaseAdapter):
    """OpenAI Responses API adapter."""

    def __init__(
        self,
        api_format: ProviderApiFormatOpenAiResponses,
        base_url: str,
        api_key: str | None,
    ):
        """Initialize OpenAI Responses adapter.

        Args:
            api_format: OpenAI Responses API format configuration.
            base_url: Base URL for OpenAI API.
            api_key: OpenAI API key or None.
        """
        super().__init__(api_format, base_url, api_key)
        self._api_format: ProviderApiFormatOpenAiResponses = api_format
        self._client = AsyncOpenAI(api_key=api_key or "", base_url=base_url)
        self._logger = Logger.get_logger(
            "providers.adapters.implementations.openai_responses_adapter"
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
        """Generate AI response using OpenAI Responses API.

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
        response_items = await self._build_response_items(
            system_prompt,
            messages,
            attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator,
            no_tool_response_prompt,
            image_detail,
            image_blobs,
        )

        reasoning_param = self._build_reasoning_param(reasoning)
        self._logger.debug(
            "llm_started",
            model_id=model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            has_system_prompt=system_prompt is not None,
        )

        text_param = self._build_text_param(verbosity)
        tools_param = self._build_tools_param(tools)
        try:
            response = await self._client.responses.create(
                model=model_id,
                input=response_items,
                max_output_tokens=max_output_tokens_count,
                # top_p=top_p,
                reasoning=reasoning_param,
                text=text_param,
                tools=tools_param,
            )

            if not response.output:
                raise Error(ErrorCode.INVALID_RESPONSE, "Response output is missing or invalid")

            result: list[MessageContent] = []
            turn_id = str(uuid4())

            for item in response.output:
                if item.type == "message":
                    for content_block in item.content:
                        if content_block.type == "output_text" and content_block.text:
                            result.append(
                                MessageContentAi(
                                    type=MessageContentType.AI,
                                    text=content_block.text,
                                    processing=False,
                                )
                            )

                elif item.type == "function_call":
                    result.append(
                        MessageContentTool(
                            type=MessageContentType.TOOL,
                            name=item.name,
                            processing=False,
                            error=None,
                            request=item.arguments,
                            response=None,
                            llm_id=item.call_id,
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
        """Stream AI response using OpenAI Responses API.

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

        response_items = await self._build_response_items(
            system_prompt,
            messages,
            attached_file_path_prompt_prefix,
            attached_file_path_prompt_separator,
            no_tool_response_prompt,
            image_detail,
            image_blobs,
        )

        turn_id = str(uuid4())
        tool_states: dict[str, dict[str, str]] = {}
        reasoning_param = self._build_reasoning_param(reasoning)
        text_param = self._build_text_param(verbosity)
        tools_param = self._build_tools_param(tools)
        chunk_count = 0

        try:
            stream = await self._client.responses.create(
                model=model_id,
                input=response_items,
                max_output_tokens=max_output_tokens_count,
                # top_p=top_p,
                reasoning=reasoning_param,
                text=text_param,
                tools=tools_param,
                stream=True,
            )

            usage: ResponseUsage | None = None
            async for event in stream:
                if event.type == "response.completed":
                    usage = event.response.usage
                elif event.type == "response.output_item.added":
                    if event.item.type == "function_call":
                        tool_states[event.item.call_id] = {
                            "id": event.item.call_id,
                            "name": event.item.name,
                        }

                        yield MessageContentTool(
                            type=MessageContentType.TOOL,
                            name=tool_states[event.item.call_id]["name"],
                            processing=False,
                            error=None,
                            request="",
                            response=None,
                            llm_id=tool_states[event.item.call_id]["id"],
                            turn_id=turn_id,
                        )

                elif event.type == "response.output_text.delta":
                    if event.delta:
                        chunk_count += 1
                        yield MessageContentAi(
                            type=MessageContentType.AI, text=event.delta, processing=False
                        )

                elif event.type == "response.function_call_arguments.delta":
                    if event.item_id in tool_states:
                        if event.delta:
                            chunk_count += 1
                            yield MessageContentTool(
                                type=MessageContentType.TOOL,
                                name=tool_states[event.item_id]["name"],
                                processing=False,
                                error=None,
                                request=event.delta,
                                response=None,
                                llm_id=tool_states[event.item_id]["id"],
                                turn_id=turn_id,
                            )

            if usage is None:
                raise Error(ErrorCode.INVALID_RESPONSE, "Responses stream ended without usage")
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

    def _build_usage(self, usage: ResponseUsage | None) -> LlmUsage:
        if usage is None:
            raise Error(ErrorCode.INVALID_RESPONSE, "Response has no usage")
        return LlmUsage(
            input_tokens_count=usage.input_tokens, output_tokens_count=usage.output_tokens
        )

    def _build_reasoning_param(self, reasoning: AgentReasoning) -> Reasoning | Omit:
        """Build reasoning parameter for OpenAI Responses API.

        Args:
            reasoning: Internal reasoning level enum.

        Returns:
            OpenAI reasoning parameter object or Omit if DEFAULT.
        """
        if reasoning == AgentReasoning.DEFAULT:
            return Omit()

        effort_map: dict[AgentReasoning, Literal["low", "medium", "high", "xhigh"]] = {
            AgentReasoning.MINIMAL: "low",
            AgentReasoning.LOW: "low",
            AgentReasoning.MEDIUM: "medium",
            AgentReasoning.HIGH: "high",
            AgentReasoning.XHIGH: "xhigh",
        }

        return Reasoning(effort=effort_map[reasoning])

    def _build_text_param(self, verbosity: AgentVerbosity) -> ResponseTextConfigParam | Omit:
        """Build text parameter for OpenAI Responses API.

        Args:
            verbosity: Internal verbosity level enum.

        Returns:
            OpenAI text parameter object or Omit if DEFAULT.
        """
        if verbosity == AgentVerbosity.DEFAULT:
            return Omit()

        verbosity_map: dict[AgentVerbosity, Literal["low", "medium", "high"]] = {
            AgentVerbosity.LOW: "low",
            AgentVerbosity.MEDIUM: "medium",
            AgentVerbosity.HIGH: "high",
        }

        return ResponseTextConfigParam(verbosity=verbosity_map[verbosity])

    def _build_tools_param(self, tools: list[Tool] | None) -> list[FunctionToolParam] | Omit:
        """Build tools parameter for OpenAI Responses API.

        Args:
            tools: List of Tool definitions.

        Returns:
            List of FunctionToolParam or Omit if no tools.
        """
        if not tools:
            return Omit()

        openai_tools: list[FunctionToolParam] = []
        for tool in tools:
            openai_tools.append(
                FunctionToolParam(
                    type="function",
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.parameters_schema,
                    strict=None,
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

    async def _build_response_items(
        self,
        system_prompt: str | None,
        messages: list[MessageContent],
        attached_file_path_prompt_prefix: str,
        attached_file_path_prompt_separator: str,
        no_tool_response_prompt: str,
        image_detail: LlmModelImageDetail,
        image_blobs: dict[str, Blob],
    ) -> ResponseInputParam:
        """Build OpenAI Responses API items from MessageContent list.

        Args:
            system_prompt: System instruction for the AI or None.
            messages: Internal message list.
            attached_file_path_prompt_prefix: Prefix added before attached file paths in the prompt.
            attached_file_path_prompt_separator: Separator between attached file paths in the prompt.
            no_tool_response_prompt: Prompt text for tools with no response.
            image_detail: Image detail level for vision capabilities.
            image_blobs: Dictionary mapping image file keys to Blob objects.

        Returns:
            List of OpenAI Responses API items.
        """
        items: ResponseInputParam = []
        if system_prompt is not None:
            items.append(
                Message(
                    type="message",
                    role="system",
                    content=[ResponseInputTextParam(type="input_text", text=system_prompt)],
                )
            )

        pending_function_outputs: list[FunctionCallOutput] = []
        current_turn_id: str | None = None

        for message in messages:
            if message.type == MessageContentType.AI:
                # Flush pending outputs before AI message
                if pending_function_outputs:
                    items.extend(pending_function_outputs.copy())
                    pending_function_outputs.clear()

                items.append(
                    ResponseOutputMessageParam(
                        type="message",
                        role="assistant",
                        id="",  # Empty string - API doesn't use this for client-constructed messages
                        status="completed",
                        content=[
                            ResponseOutputTextParam(
                                type="output_text", text=message.text, annotations=[]
                            )
                        ],
                    )
                )
                current_turn_id = None

            if message.type == MessageContentType.TOOL:
                # Check if turn_id changed - flush if so
                if current_turn_id and current_turn_id != message.turn_id:
                    if pending_function_outputs:
                        items.extend(pending_function_outputs.copy())
                        pending_function_outputs.clear()

                # Add function_call immediately
                items.append(
                    ResponseFunctionToolCallParam(
                        type="function_call",
                        call_id=message.llm_id,
                        name=message.name,
                        arguments=message.request,
                    )
                )

                # Build function_call_output with text and images
                output_content: ResponseFunctionCallOutputItemListParam = []

                # Add text if present
                response_text = (
                    message.response.text if message.response and message.response.text else None
                )
                if response_text:
                    output_content.append(
                        ResponseInputTextContentParam(type="input_text", text=response_text)
                    )

                # Add images if present
                if message.response and message.response.image_file_keys:
                    for file_key in message.response.image_file_keys:
                        blob_data = image_blobs.get(file_key)
                        if blob_data is None:
                            raise Error(
                                ErrorCode.INVALID_ARGUMENT,
                                f"Image blob not found for key: {file_key}",
                            )
                        output_content.append(
                            ResponseInputImageContentParam(
                                type="input_image",
                                detail=self._map_image_detail(image_detail),
                                image_url=f"data:{blob_data.content_type};base64,{base64.b64encode(blob_data.content).decode('utf-8')}",
                            )
                        )

                pending_function_outputs.append(
                    FunctionCallOutput(
                        type="function_call_output",
                        call_id=message.llm_id,
                        output=(
                            output_content
                            if output_content
                            else (message.error if message.error else no_tool_response_prompt)
                        ),
                    )
                )

                # Update turn tracking
                current_turn_id = message.turn_id

            elif (
                message.type == MessageContentType.USER
                or message.type == MessageContentType.INTERNAL
            ):
                # Flush pending outputs before user message
                if pending_function_outputs:
                    items.extend(pending_function_outputs.copy())
                    pending_function_outputs.clear()

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

                items.append(
                    Message(
                        type="message",
                        role="user",
                        content=[ResponseInputTextParam(type="input_text", text=message_text)],
                    )
                )
                current_turn_id = None

        # Flush any remaining pending outputs
        if pending_function_outputs:
            items.extend(pending_function_outputs.copy())
            pending_function_outputs.clear()

        return items
