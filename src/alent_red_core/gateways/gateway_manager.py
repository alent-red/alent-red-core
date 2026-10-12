import asyncio
from uuid import UUID

from ..common import Logger
from ..models import (
    Conversation,
    ConversationInput,
    ConversationSender,
    Error,
    ErrorCode,
    GatewayInput,
    Message,
    MessageContent,
    MessageContentType,
    MessageContentUser,
    MessageInput,
    PreferenceKey,
    PreferenceValueType,
)
from ..database import Database
from ..blob import BlobStorage
from ..looper import Looper
from .base_gateway import BaseGateway
from .gateway_builder import GatewayBuilder
from .gateway_reporter import GatewayReporter


class GatewayManager(GatewayReporter):
    """Manages lifecycle and orchestration of all gateway instances."""

    def __init__(self, looper: Looper, database: Database, blob: BlobStorage):
        """Initialize gateway manager.

        Args:
            looper: Looper instance for triggering conversation processing.
            database: Database instance.
            blob: Blob storage instance.
        """
        self._looper = looper
        self._database = database
        self._blob = blob
        self.gateways: dict[UUID, BaseGateway] = {}
        self._tool_separator: str = ""
        self._conversation_save_task: asyncio.Task[None] | None = None
        self._message_save_task: asyncio.Task[None] | None = None
        self._chat_locks: dict[tuple[UUID, str], asyncio.Lock] = {}
        self._logger = Logger.get_logger("gateways.gateway_manager")

    async def setup(self) -> None:
        """Setup the gateway manager and start watching conversation saves."""
        self._logger.debug("setup_started")

        await self._load_preferences()

        gateways = await self._database.gateways.get_all()
        for gateway in gateways:
            gateway_instance = await GatewayBuilder.build(gateway, self._blob, self)
            self.gateways[gateway.id] = gateway_instance

        self._conversation_save_task = asyncio.create_task(self._watch_conversation_saves())
        self._message_save_task = asyncio.create_task(self._watch_message_saves())

        self._logger.debug("setup_completed", count=len(self.gateways))

    async def refresh(self) -> None:
        """Refresh all gateways from database."""
        self._logger.debug("refresh_started")

        await self._load_preferences()

        gateways = await self._database.gateways.get_all()
        db_gateway_ids = {gateway.id for gateway in gateways}
        current_gateway_ids = set(self.gateways.keys())

        for gateway in gateways:
            if gateway.id in self.gateways:
                await self.gateways[gateway.id].refresh(gateway.config)
            else:
                gateway_instance = await GatewayBuilder.build(gateway, self._blob, self)
                self.gateways[gateway.id] = gateway_instance

        removed_gateway_ids = current_gateway_ids - db_gateway_ids
        for gateway_id in removed_gateway_ids:
            await self.gateways[gateway_id].clean()
            del self.gateways[gateway_id]

        self._logger.debug(
            "refresh_completed",
            count=len(self.gateways),
            added=len(db_gateway_ids - current_gateway_ids),
            removed=len(removed_gateway_ids),
        )

    async def clean(self) -> None:
        """Clean the gateway manager, stop watching, and cleanup all gateways."""
        self._logger.debug("clean_started", count=len(self.gateways))

        if self._conversation_save_task is not None:
            self._conversation_save_task.cancel()
            await asyncio.gather(self._conversation_save_task, return_exceptions=True)
            self._conversation_save_task = None

        if self._message_save_task is not None:
            self._message_save_task.cancel()
            await asyncio.gather(self._message_save_task, return_exceptions=True)
            self._message_save_task = None

        for gateway in self.gateways.values():
            await gateway.clean()
        self.gateways.clear()

        self._logger.debug("clean_completed")

    async def _watch_conversation_saves(self) -> None:
        """Watch the conversation bus and dispatch each save to its gateway."""
        async for conversation in self._database.conversations.bus.watch_saves():
            await self._handle_conversation_save(conversation)

    async def _watch_message_saves(self) -> None:
        """Watch the message bus and dispatch each save to its gateway."""
        async for message in self._database.messages.bus.watch_saves():
            await self._handle_message_save(message)

    async def _handle_conversation_save(self, conversation: Conversation) -> None:
        """Dispatch a conversation save to its gateway.

        Args:
            conversation: The saved conversation.

        Raises:
            Error: If the conversation references a gateway that is missing its
                external identifier or is not currently loaded.
        """
        resolved = self._resolve_gateway(conversation)
        if resolved is None:
            return
        gateway, _, gateway_external_id = resolved

        await gateway.handle_conversation_processing(gateway_external_id, conversation.processing)

        if conversation.error_code is not None:
            error = Error(
                conversation.error_code,
                conversation.error_message or conversation.error_code.value,
            )
            await gateway.handle_conversation_error(gateway_external_id, error)

    async def _handle_message_save(self, message: Message) -> None:
        """Dispatch a message save to its conversation's gateway.

        Args:
            message: The saved message.

        Raises:
            Error: If the conversation is not found, references a gateway that is
                missing its external identifier, or the gateway is not loaded.
        """
        if message.content.type == MessageContentType.USER:
            return

        if message.content.type == MessageContentType.AI and message.content.processing:
            return

        conversation = await self._database.conversations.get(
            conversation_id=message.conversation_id
        )
        if conversation is None:
            raise Error(ErrorCode.NOT_FOUND, f"Conversation {message.conversation_id} not found")

        resolved = self._resolve_gateway(conversation)
        if resolved is None:
            return
        gateway, gateway_id, gateway_external_id = resolved

        gateway_record = await self._database.gateways.get(gateway_id=gateway_id)
        if gateway_record is None:
            raise Error(ErrorCode.NOT_FOUND, f"Gateway {gateway_id} not found")

        if (
            not gateway_record.send_detailed_messages
            and message.content.type != MessageContentType.AI
        ):
            return

        rendered = self._render_message(message.content)
        if rendered is None:
            return
        text, image_file_keys = rendered

        await gateway.handle_message(gateway_external_id, text, image_file_keys)

    def _render_message(self, content: MessageContent) -> tuple[str | None, list[str]] | None:
        """Render a message content into the text and image keys to send.

        Args:
            content: The message content to render.

        Returns:
            A tuple of the text to send (or None for images only) and the image
            blob keys to send, or None when there is nothing to send.

        Raises:
            Error: If the content type is not supported.
        """
        if content.type == MessageContentType.AI:
            return content.text, []

        if content.type == MessageContentType.INTERNAL:
            return f"🔔 {content.text}", []

        if content.type == MessageContentType.TOOL:
            tool_name = self._render_tool_name(content.name)
            if content.error is not None:
                return f"❌ Tool {tool_name}: error occured", []
            if content.processing:
                return f"⚙️ Tool {tool_name}", []
            if content.response is not None and content.response.image_file_keys:
                return None, list(content.response.image_file_keys)
            return None

        raise Error(
            ErrorCode.NOT_SUPPORTED,
            f"Unsupported message content type: {content.type}",
        )

    def _render_tool_name(self, name: str) -> str:
        """Render a prefixed tool name into a human-readable label.

        Splits on the tool separator, uppercases every part except the last,
        humanizes the last part (underscores to spaces, capitalized), and joins
        with " - " (for example, "ui__move_pointer" becomes "UI - Move pointer").

        Args:
            name: Prefixed tool name.

        Returns:
            Human-readable tool label.
        """
        parts = name.split(self._tool_separator)
        last_part = parts[-1].replace("_", " ").strip().capitalize()
        rendered_parts = [part.upper() for part in parts[:-1]] + [last_part]
        return " - ".join(rendered_parts)

    async def handle_message(
        self,
        gateway_id: UUID,
        gateway_external_id: str,
        content: MessageContentUser,
        sender: ConversationSender,
    ) -> None:
        """Receive a new user message from a gateway and process it.

        Finds the conversation for the gateway origin or creates one bound to the
        gateway's agent, saves the user message, and triggers processing.

        A per-chat lock serializes concurrent calls for the same chat so that the
        find-or-create conversation step is atomic and messages are enqueued in order.

        Args:
            gateway_id: Identifier of the gateway the message originates from.
            gateway_external_id: External identifier of the conversation on the gateway.
            content: The user message content.
            sender: Identity of the sender on the gateway.

        Raises:
            Error: If the gateway is not found.
        """
        self._logger.debug(
            "handle_message_started",
            gateway_id=str(gateway_id),
            gateway_external_id=gateway_external_id,
        )

        chat_key = (gateway_id, gateway_external_id)
        if chat_key not in self._chat_locks:
            self._chat_locks[chat_key] = asyncio.Lock()

        async with self._chat_locks[chat_key]:
            conversation = await self._database.conversations.get_by_gateway(
                gateway_id=gateway_id, gateway_external_id=gateway_external_id
            )

            if conversation is None:
                gateway = await self._database.gateways.get(gateway_id=gateway_id)
                if gateway is None:
                    raise Error(ErrorCode.NOT_FOUND, f"Gateway {gateway_id} not found")

                conversation = await self._database.conversations.save(
                    ConversationInput(
                        name=None,
                        agent_id=gateway.agent_id,
                        processing=False,
                        error_code=None,
                        error_message=None,
                        context_tokens_count=None,
                        gateway_id=gateway_id,
                        gateway_external_id=gateway_external_id,
                        sender=sender,
                    ),
                    None,
                )

            await self._database.messages.save(
                MessageInput(content=content, conversation_id=conversation.id),
                None,
            )

            await self._looper.process(conversation)

        self._logger.debug(
            "handle_message_completed",
            gateway_id=str(gateway_id),
            conversation_id=str(conversation.id),
        )

    async def handle_error(self, gateway_id: UUID, error: Error | None) -> None:
        """Record a gateway-level error, or clear it when recovered.

        Args:
            gateway_id: Identifier of the gateway reporting the error.
            error: Error that occurred on the gateway, or None to clear it.

        Raises:
            Error: If the gateway is not found.
        """
        self._logger.debug(
            "handle_error_started",
            gateway_id=str(gateway_id),
            error_code=error.code.value if error is not None else None,
        )

        gateway = await self._database.gateways.get(gateway_id=gateway_id)
        if gateway is None:
            raise Error(ErrorCode.NOT_FOUND, f"Gateway {gateway_id} not found")

        await self._database.gateways.save(
            GatewayInput(
                name=gateway.name,
                send_detailed_messages=gateway.send_detailed_messages,
                error_code=error.code if error is not None else None,
                error_message=(str(error).strip() or None) if error is not None else None,
                config=gateway.config,
                agent_id=gateway.agent_id,
            ),
            gateway_id,
        )

        self._logger.debug("handle_error_completed", gateway_id=str(gateway_id))

    def _resolve_gateway(self, conversation: Conversation) -> tuple[BaseGateway, UUID, str] | None:
        """Resolve the gateway instance, id, and external identifier for a conversation.

        Args:
            conversation: The conversation to resolve.

        Returns:
            The gateway instance, its id, and its external identifier, or None if
            the conversation does not originate from a gateway.

        Raises:
            Error: If the conversation is missing its external identifier or the
                gateway is not currently loaded.
        """
        if conversation.gateway_id is None:
            return None

        if conversation.gateway_external_id is None:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                "Conversation has gateway_id but no gateway_external_id",
            )

        if conversation.gateway_id not in self.gateways:
            raise Error(ErrorCode.NOT_FOUND, f"Gateway {conversation.gateway_id} not found")

        return (
            self.gateways[conversation.gateway_id],
            conversation.gateway_id,
            conversation.gateway_external_id,
        )

    async def _load_preferences(self) -> None:
        """Load required preferences from the database.

        Raises:
            Error: If a required preference is not found or has an invalid type.
        """
        tool_separator_preference = await self._database.preferences.get(
            PreferenceKey.BRICK_TOOL_NAME_SEPARATOR
        )
        if tool_separator_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.BRICK_TOOL_NAME_SEPARATOR} not found",
            )
        if tool_separator_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.BRICK_TOOL_NAME_SEPARATOR} must be string type",
            )
        self._tool_separator = tool_separator_preference.value.value
