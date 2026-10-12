import asyncio
import time
from uuid import UUID

from ..common import AttachedFilePathsPrompt, Logger
from ..models import (
    Agent,
    Conversation,
    ConversationInput,
    Error,
    ErrorCode,
    LlmModel,
    LlmUsage,
    MessageContent,
    MessageContentAi,
    MessageContentTool,
    MessageContentType,
    MessageInput,
    PreferenceKey,
    PreferenceValueType,
    Tool,
)
from ..database import Database
from ..blob import BlobStorage
from ..providers import ProviderManager, ProviderManagerBuilder
from ..bricks import BrickManager, BrickManagerBuilder


class Looper:
    """Central orchestrator managing the conversation processing loop."""

    _partial_save_interval_seconds = 0.15

    def __init__(self, database: Database, blob: BlobStorage):
        """Initialize looper.

        Args:
            database: Database instance.
            blob: Blob storage instance.
        """
        self._database = database
        self._blob = blob
        self._providers: ProviderManager
        self._bricks: BrickManager
        self._system_prompt: str | None = None
        self._agent_prompt_placeholder: str | None = None
        self._brick_prompt_placeholder: str | None = None
        self._attached_file_path_prompt_prefix: str | None = None
        self._attached_file_path_prompt_separator: str | None = None
        self._llm_stream: bool | None = None
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._logger = Logger.get_logger("looper.looper")

    async def setup(self) -> None:
        """Setup the looper and initialize providers and bricks.

        Raises:
            Error: If required preferences are not found or have invalid types.
        """
        self._logger.debug("setup_started")

        await self._load_preferences()
        self._providers = await ProviderManagerBuilder.build(self._database, self._blob)
        self._bricks = await BrickManagerBuilder.build(
            self, self._providers, self._database, self._blob
        )

        self._logger.debug("setup_completed")

    async def refresh(self) -> None:
        """Refresh providers and bricks.

        Raises:
            Error: If required preferences are not found or have invalid types.
        """
        self._logger.debug("refresh_started")

        await self._load_preferences()
        await self._providers.refresh()
        await self._bricks.refresh()

        self._logger.debug("refresh_completed")

    async def clean(self) -> None:
        """Clean the looper and cleanup providers and bricks."""
        self._logger.debug("clean_started")

        await self._bricks.clean()
        await self._providers.clean()

        self._logger.debug("clean_completed")

    async def process(self, conversation: Conversation) -> None:
        """Start processing a conversation in the background.

        If the conversation is already being processed, the current task is
        paused first and a new one is started.

        Args:
            conversation: Conversation to process.
        """
        await self.pause(conversation)

        self._logger.info("process_started", conversation_id=str(conversation.id))

        await self._save_conversation_state(
            conversation, processing=True, error_code=None, error_message=None
        )

        self._tasks[conversation.id] = asyncio.create_task(self._process(conversation))

    async def pause(self, conversation: Conversation) -> None:
        """Pause an in-progress conversation processing.

        If the conversation is not currently being processed, returns silently.

        Args:
            conversation: Conversation to pause.
        """
        task = self._tasks.pop(conversation.id, None)
        if task is None:
            return

        self._logger.info("pause_started", conversation_id=str(conversation.id))
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self._logger.info("pause_completed", conversation_id=str(conversation.id))

    async def _process(self, conversation: Conversation) -> None:
        """Run the conversation processing loop.

        Args:
            conversation: Conversation to process.
        """
        try:
            if self._llm_stream is None:
                raise Error(ErrorCode.INTERNAL, "LLM stream preference not loaded")

            agent = (
                await self._database.agents.get(agent_id=conversation.agent_id)
                if conversation.agent_id is not None
                else None
            )

            if agent is None:
                raise Error(ErrorCode.INVALID_RESPONSE, "Conversation agent not found")

            llm_model = (
                await self._database.llm_models.get(llm_model_id=agent.llm_model_id)
                if agent.llm_model_id is not None
                else None
            )

            if llm_model is None:
                raise Error(ErrorCode.INVALID_RESPONSE, "Conversation agent LLM model not found")

            await self._bricks.before_loop(conversation)

            brick_prompt = await self._bricks.get_prompt(conversation)
            tools = await self._bricks.get_tools(conversation)

            system_prompt = self._build_system_prompt(
                agent.prompt, agent.attached_file_paths, brick_prompt
            )

            loop = True
            while loop:
                messages = await self._database.messages.get_all(conversation_id=conversation.id)

                message_contents = [message.content for message in messages]

                if self._llm_stream:
                    loop = await self._process_stream(
                        system_prompt=system_prompt,
                        tools=tools,
                        message_contents=message_contents,
                        agent=agent,
                        llm_model=llm_model,
                        conversation=conversation,
                    )
                else:
                    loop = await self._process_non_stream(
                        system_prompt=system_prompt,
                        tools=tools,
                        message_contents=message_contents,
                        agent=agent,
                        llm_model=llm_model,
                        conversation=conversation,
                    )

            await self._save_conversation_state(
                conversation, processing=False, error_code=None, error_message=None
            )
        except asyncio.CancelledError:
            await self._save_conversation_state(
                conversation, processing=False, error_code=None, error_message=None
            )
        except Error as error:
            await self._save_conversation_state(
                conversation,
                processing=False,
                error_code=error.code,
                error_message=str(error).strip() or None,
            )
        except Exception as exception:
            await self._save_conversation_state(
                conversation, processing=False, error_code=ErrorCode.UNKNOWN, error_message=None
            )
        finally:
            self._tasks.pop(conversation.id, None)
            await self._bricks.after_loop(conversation)
            self._logger.info("process_completed", conversation_id=str(conversation.id))

    async def _process_non_stream(
        self,
        system_prompt: str | None,
        tools: list[Tool] | None,
        message_contents: list[MessageContent],
        agent: Agent,
        llm_model: LlmModel,
        conversation: Conversation,
    ) -> bool:
        """Process conversation using non-streaming LLM call.

        Args:
            system_prompt: System prompt or None.
            tools: List of available tools.
            agent: Agent owning this conversation (provides reasoning/verbosity).
            llm_model: LLM model to use for generation.
            conversation: Conversation being processed.

        Returns:
            Whether processing should continue.
        """
        self._logger.debug(
            "process_non_stream_started",
            conversation_id=str(conversation.id),
            message_count=len(message_contents),
            tool_count=len(tools) if tools else 0,
        )

        response = await self._providers.llm(
            system_prompt=system_prompt,
            messages=message_contents,
            tools=tools,
            llm_model=llm_model,
            reasoning=agent.reasoning,
            verbosity=agent.verbosity,
        )
        response_contents = response.contents

        if not response_contents:
            raise Error(ErrorCode.INVALID_RESPONSE, "LLM response is empty")

        await self._save_context_tokens_count(conversation, response.usage)

        for content in response_contents:
            await self._flush_message_content(content, conversation, None)

        self._logger.debug(
            "process_non_stream_completed",
            conversation_id=str(conversation.id),
            response_count=len(response_contents),
        )

        return response_contents[-1].type == MessageContentType.TOOL

    async def _process_stream(
        self,
        system_prompt: str | None,
        tools: list[Tool] | None,
        message_contents: list[MessageContent],
        agent: Agent,
        llm_model: LlmModel,
        conversation: Conversation,
    ) -> bool:
        """Process conversation using streaming LLM call.

        The content being streamed is persisted progressively on a single message id,
        throttled by _partial_save_interval_seconds, so watchers see it grow. An AI
        message is created at the first non-blank chunk and closed with
        processing=False; a tool request is created at its first chunk and completed
        by the flush that executes it.

        Args:
            system_prompt: System prompt or None.
            tools: List of available tools.
            message_contents: Conversation history.
            agent: Agent owning this conversation (provides reasoning/verbosity).
            llm_model: LLM model to use for generation.
            conversation: Conversation being processed.

        Returns:
            Whether processing should continue.
        """
        self._logger.debug(
            "process_stream_started",
            conversation_id=str(conversation.id),
            message_count=len(message_contents),
            tool_count=len(tools) if tools else 0,
        )

        current_message_content: MessageContent | None = None
        current_message_id: UUID | None = None
        last_partial_save_at = 0.0
        usage: LlmUsage | None = None

        try:
            async for item in self._providers.llm_stream(
                system_prompt=system_prompt,
                messages=message_contents,
                tools=tools,
                llm_model=llm_model,
                reasoning=agent.reasoning,
                verbosity=agent.verbosity,
            ):
                if isinstance(item, LlmUsage):
                    usage = item
                    continue
                chunk = item

                if current_message_content is None:
                    current_message_content = chunk
                elif (
                    chunk.type == MessageContentType.AI
                    and current_message_content.type == MessageContentType.AI
                ):
                    current_message_content = MessageContentAi(
                        text=current_message_content.text + chunk.text, processing=False
                    )
                elif (
                    chunk.type == MessageContentType.TOOL
                    and current_message_content.type == MessageContentType.TOOL
                    and chunk.llm_id == current_message_content.llm_id
                ):
                    current_message_content = MessageContentTool(
                        name=current_message_content.name,
                        processing=current_message_content.processing,
                        error=current_message_content.error,
                        request=current_message_content.request + chunk.request,
                        response=current_message_content.response,
                        llm_id=current_message_content.llm_id,
                        turn_id=current_message_content.turn_id,
                    )
                elif chunk.type in (MessageContentType.AI, MessageContentType.TOOL):
                    await self._flush_message_content(
                        current_message_content, conversation, current_message_id
                    )
                    current_message_content = chunk
                    current_message_id = None
                    last_partial_save_at = 0.0
                else:
                    raise Error(
                        ErrorCode.NOT_SUPPORTED,
                        f"Unsupported stream chunk type: {chunk.type}",
                    )

                now = time.monotonic()
                if now - last_partial_save_at >= self._partial_save_interval_seconds:
                    current_message_id = await self._save_partial_message_content(
                        current_message_content, conversation, current_message_id
                    )
                    last_partial_save_at = now
        except asyncio.CancelledError:
            if current_message_content is not None and current_message_id is not None:
                await self._close_partial_message_content(
                    current_message_content, conversation, current_message_id
                )
            raise

        if current_message_content is None:
            raise Error(ErrorCode.INVALID_RESPONSE, "LLM stream response is empty")
        if usage is None:
            raise Error(ErrorCode.INVALID_RESPONSE, "LLM stream ended without usage")

        await self._save_context_tokens_count(conversation, usage)
        await self._flush_message_content(current_message_content, conversation, current_message_id)

        self._logger.debug(
            "process_stream_completed",
            conversation_id=str(conversation.id),
        )

        return current_message_content.type == MessageContentType.TOOL

    async def _save_context_tokens_count(self, conversation: Conversation, usage: LlmUsage) -> None:
        """Record what the conversation weighs after an LLM call.

        The call's input is everything the conversation held when it was sent, and its
        output now belongs to the history, so their sum is the current context size.

        Args:
            conversation: Conversation being processed (updated in place).
            usage: Usage of the call that just completed.
        """
        conversation.context_tokens_count = usage.input_tokens_count + usage.output_tokens_count
        await self._save_conversation_state(
            conversation, processing=True, error_code=None, error_message=None
        )

    async def _save_conversation_state(
        self,
        conversation: Conversation,
        processing: bool,
        error_code: ErrorCode | None,
        error_message: str | None,
    ) -> None:
        await self._database.conversations.save(
            ConversationInput(
                name=conversation.name,
                agent_id=conversation.agent_id,
                processing=processing,
                error_code=error_code,
                error_message=error_message,
                context_tokens_count=conversation.context_tokens_count,
                gateway_id=conversation.gateway_id,
                gateway_external_id=conversation.gateway_external_id,
                sender=conversation.sender,
            ),
            conversation.id,
        )

    async def _save_partial_message_content(
        self, content: MessageContent, conversation: Conversation, message_id: UUID | None
    ) -> UUID | None:
        """Persist an in-progress content with processing=True on its message id.

        Args:
            content: Content accumulated so far.
            conversation: Conversation being processed.
            message_id: Existing message id, or None if not created yet.

        Returns:
            The message id to keep updating, or None when there is nothing to persist
            yet (an AI text that is still blank).
        """
        if content.type == MessageContentType.AI:
            if message_id is None and not content.text.strip():
                return None
            partial: MessageContent = MessageContentAi(text=content.text, processing=True)
        elif content.type == MessageContentType.TOOL:
            partial = MessageContentTool(
                name=content.name,
                processing=True,
                error=None,
                request=content.request,
                response=None,
                llm_id=content.llm_id,
                turn_id=content.turn_id,
            )
        else:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"Unsupported response content type: {content.type}",
            )

        saved = await self._database.messages.save(
            MessageInput(content=partial, conversation_id=conversation.id), message_id
        )
        return saved.id

    async def _close_partial_message_content(
        self, content: MessageContent, conversation: Conversation, message_id: UUID
    ) -> None:
        """Leave an interrupted content in a consistent state (processing=False).

        An interrupted AI text keeps what was received. An interrupted tool request is
        kept without response, which adapters replay as a tool call with no result.

        Args:
            content: Content accumulated when the processing was cancelled.
            conversation: Conversation being processed.
            message_id: Message id of the partial content.
        """
        if content.type == MessageContentType.AI:
            closed: MessageContent = MessageContentAi(text=content.text, processing=False)
        elif content.type == MessageContentType.TOOL:
            closed = MessageContentTool(
                name=content.name,
                processing=False,
                error=None,
                request=content.request if content.request else "{}",
                response=None,
                llm_id=content.llm_id,
                turn_id=content.turn_id,
            )
        else:
            return

        await self._database.messages.save(
            MessageInput(content=closed, conversation_id=conversation.id), message_id
        )

    async def _flush_message_content(
        self, content: MessageContent, conversation: Conversation, message_id: UUID | None
    ) -> None:
        if content.type == MessageContentType.AI:
            if not content.text.strip():
                self._logger.debug("skip_blank_ai_message", conversation_id=str(conversation.id))
                return
            self._logger.debug("flush_ai_message", conversation_id=str(conversation.id))
            await self._database.messages.save(
                MessageInput(
                    content=MessageContentAi(text=content.text, processing=False),
                    conversation_id=conversation.id,
                ),
                message_id,
            )
        elif content.type == MessageContentType.TOOL:
            self._logger.debug(
                "flush_tool_request_started",
                conversation_id=str(conversation.id),
                tool_name=content.name,
            )
            request = content.request if content.request else "{}"

            tool_message = await self._database.messages.save(
                MessageInput(
                    content=MessageContentTool(
                        name=content.name,
                        processing=True,
                        error=None,
                        request=request,
                        response=None,
                        llm_id=content.llm_id,
                        turn_id=content.turn_id,
                    ),
                    conversation_id=conversation.id,
                ),
                message_id,
            )
            try:
                tool_response = await self._bricks.handle_tool_request(
                    content.name, request, conversation
                )
                await self._database.messages.save(
                    MessageInput(
                        content=MessageContentTool(
                            name=content.name,
                            processing=False,
                            error=None,
                            request=request,
                            response=tool_response,
                            llm_id=content.llm_id,
                            turn_id=content.turn_id,
                        ),
                        conversation_id=conversation.id,
                    ),
                    tool_message.id,
                )
                self._logger.debug(
                    "flush_tool_request_completed",
                    conversation_id=str(conversation.id),
                    tool_name=content.name,
                )
            except Error as tool_error:
                await self._database.messages.save(
                    MessageInput(
                        content=MessageContentTool(
                            name=content.name,
                            processing=False,
                            error=tool_error.code,
                            request=content.request,
                            response=None,
                            llm_id=content.llm_id,
                            turn_id=content.turn_id,
                        ),
                        conversation_id=conversation.id,
                    ),
                    tool_message.id,
                )
            except Exception as exception:
                await self._database.messages.save(
                    MessageInput(
                        content=MessageContentTool(
                            name=content.name,
                            processing=False,
                            error=ErrorCode.UNKNOWN,
                            request=content.request,
                            response=None,
                            llm_id=content.llm_id,
                            turn_id=content.turn_id,
                        ),
                        conversation_id=conversation.id,
                    ),
                    tool_message.id,
                )
        else:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"Unsupported response content type: {content.type}",
            )

    def _build_system_prompt(
        self,
        agent_prompt: str | None,
        agent_attached_file_paths: list[str],
        brick_prompt: str | None,
    ) -> str | None:
        if self._system_prompt is None:
            raise Error(ErrorCode.INTERNAL, "System prompt preference not loaded")
        if self._agent_prompt_placeholder is None:
            raise Error(ErrorCode.INTERNAL, "Agent prompt placeholder preference not loaded")
        if self._brick_prompt_placeholder is None:
            raise Error(ErrorCode.INTERNAL, "Brick prompt placeholder preference not loaded")
        if self._attached_file_path_prompt_prefix is None:
            raise Error(ErrorCode.INTERNAL, "Attached file path prefix preference not loaded")
        if self._attached_file_path_prompt_separator is None:
            raise Error(ErrorCode.INTERNAL, "Attached file path separator preference not loaded")

        rendered_agent_prompt = AttachedFilePathsPrompt.render(
            text=agent_prompt,
            attached_file_paths=agent_attached_file_paths,
            prefix=self._attached_file_path_prompt_prefix,
            separator=self._attached_file_path_prompt_separator,
        )

        result = self._system_prompt
        result = result.replace(self._agent_prompt_placeholder, rendered_agent_prompt or "")
        result = result.replace(self._brick_prompt_placeholder, brick_prompt or "")
        return result.strip() or None

    async def _load_preferences(self) -> None:
        """Load required preferences from database.

        Raises:
            Error: If required preferences are not found or have invalid types.
        """
        system_prompt_preference = await self._database.preferences.get(PreferenceKey.SYSTEM_PROMPT)
        if system_prompt_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.SYSTEM_PROMPT} not found",
            )
        if system_prompt_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.SYSTEM_PROMPT} must be string type",
            )
        self._system_prompt = system_prompt_preference.value.value

        agent_prompt_placeholder_preference = await self._database.preferences.get(
            PreferenceKey.AGENT_PROMPT_PLACEHOLDER
        )
        if agent_prompt_placeholder_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.AGENT_PROMPT_PLACEHOLDER} not found",
            )
        if agent_prompt_placeholder_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.AGENT_PROMPT_PLACEHOLDER} must be string type",
            )
        self._agent_prompt_placeholder = agent_prompt_placeholder_preference.value.value

        brick_prompt_placeholder_preference = await self._database.preferences.get(
            PreferenceKey.BRICK_PROMPT_PLACEHOLDER
        )
        if brick_prompt_placeholder_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.BRICK_PROMPT_PLACEHOLDER} not found",
            )
        if brick_prompt_placeholder_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.BRICK_PROMPT_PLACEHOLDER} must be string type",
            )
        self._brick_prompt_placeholder = brick_prompt_placeholder_preference.value.value

        self._attached_file_path_prompt_prefix = await self._load_string_preference(
            PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX
        )
        self._attached_file_path_prompt_separator = await self._load_string_preference(
            PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR
        )

        llm_stream_preference = await self._database.preferences.get(PreferenceKey.LLM_STREAM)
        if llm_stream_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.LLM_STREAM} not found",
            )
        if llm_stream_preference.value.type != PreferenceValueType.BOOL:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.LLM_STREAM} must be bool type",
            )
        self._llm_stream = llm_stream_preference.value.value

    async def _load_string_preference(self, key: PreferenceKey) -> str:
        preference = await self._database.preferences.get(key)
        if preference is None:
            raise Error(ErrorCode.NOT_FOUND, f"Required preference {key} not found")
        if preference.value.type != PreferenceValueType.STRING:
            raise Error(ErrorCode.INVALID_RESPONSE, f"Preference {key} must be string type")
        return preference.value.value
