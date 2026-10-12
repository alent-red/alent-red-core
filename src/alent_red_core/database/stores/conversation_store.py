from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import select, column, desc
from ...common import Logger
from ...models import Conversation, ConversationInput, Message, Error, ErrorCode
from ..utils import handle_database_errors
from ..buses import ConversationBus

if TYPE_CHECKING:
    from ..database import Database


class ConversationStore:
    """Manages conversation storage operations."""

    def __init__(self, database: Database):
        """Initialize conversation store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.conversation_store")
        self.bus = ConversationBus()

    @handle_database_errors
    async def get_all(self, agent_id: UUID | None = None) -> list[Conversation]:
        """Get all conversations sorted by updated_at descending.

        Args:
            agent_id: Optional agent ID to filter by.

        Returns:
            List of all conversations, optionally filtered by agent, sorted by updated_at DESC.
        """
        if agent_id:
            self._logger.debug("get_all_started", agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_started")

        async with self._database.session() as session:
            if agent_id:
                result = await session.execute(
                    select(Conversation)
                    .where(column("agent_id") == agent_id)
                    .order_by(desc(column("updated_at")))
                )
            else:
                result = await session.execute(
                    select(Conversation).order_by(desc(column("updated_at")))
                )
            conversations = list(result.scalars().all())

        if agent_id:
            self._logger.debug(
                "get_all_completed", count=len(conversations), agent_id=str(agent_id)
            )
        else:
            self._logger.debug("get_all_completed", count=len(conversations))

        return conversations

    @handle_database_errors
    async def get(self, conversation_id: UUID) -> Conversation | None:
        """Get conversation by ID.

        Args:
            conversation_id: Conversation ID.

        Returns:
            Conversation if found, None otherwise.
        """
        self._logger.debug("get_started", conversation_id=str(conversation_id))

        async with self._database.session() as session:
            conversation = await session.get(Conversation, conversation_id)

        self._logger.debug(
            "get_completed", conversation_id=str(conversation_id), found=conversation is not None
        )

        return conversation

    @handle_database_errors
    async def get_by_gateway(
        self, gateway_id: UUID, gateway_external_id: str
    ) -> Conversation | None:
        """Get a conversation by its gateway origin.

        Args:
            gateway_id: Gateway ID the conversation originates from.
            gateway_external_id: External identifier of the conversation on the gateway.

        Returns:
            Conversation if found, None otherwise.
        """
        self._logger.debug(
            "get_by_gateway_started",
            gateway_id=str(gateway_id),
            gateway_external_id=gateway_external_id,
        )

        async with self._database.session() as session:
            result = await session.execute(
                select(Conversation)
                .where(column("gateway_id") == gateway_id)
                .where(column("gateway_external_id") == gateway_external_id)
            )
            conversation = result.scalars().first()

        self._logger.debug(
            "get_by_gateway_completed",
            gateway_id=str(gateway_id),
            gateway_external_id=gateway_external_id,
            found=conversation is not None,
        )

        return conversation

    @handle_database_errors
    async def save(
        self, conversation_input: ConversationInput, conversation_id: UUID | None
    ) -> Conversation:
        """Save conversation (create new or update existing).

        Args:
            conversation_input: Conversation data to save.
            conversation_id: Conversation ID to update (None for new conversation).

        Returns:
            Saved conversation.

        Raises:
            Error: If conversation not found (update mode) or foreign key violation.
        """
        if conversation_id:
            self._logger.debug("save_started", conversation_id=str(conversation_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if conversation_id:
                conversation = await session.get(Conversation, conversation_id)
                if not conversation:
                    raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

                conversation.name = conversation_input.name
                conversation.agent_id = conversation_input.agent_id
                conversation.processing = conversation_input.processing
                conversation.error_code = conversation_input.error_code
                conversation.error_message = conversation_input.error_message
                conversation.context_tokens_count = conversation_input.context_tokens_count
                conversation.gateway_id = conversation_input.gateway_id
                conversation.gateway_external_id = conversation_input.gateway_external_id
                conversation.sender = conversation_input.sender
            else:
                conversation = Conversation(
                    name=conversation_input.name,
                    agent_id=conversation_input.agent_id,
                    processing=conversation_input.processing,
                    error_code=conversation_input.error_code,
                    error_message=conversation_input.error_message,
                    context_tokens_count=conversation_input.context_tokens_count,
                    gateway_id=conversation_input.gateway_id,
                    gateway_external_id=conversation_input.gateway_external_id,
                    sender=conversation_input.sender,
                )
                session.add(conversation)

            await session.commit()
            await session.refresh(conversation)

        if conversation_id:
            self._logger.debug(
                "save_completed", conversation_id=str(conversation.id), mode="update"
            )
        else:
            self._logger.debug(
                "save_completed", conversation_id=str(conversation.id), mode="create"
            )

        self.bus.notify_save(conversation)

        return conversation

    @handle_database_errors
    async def delete(self, conversation_id: UUID) -> None:
        """Delete conversation by ID.

        Args:
            conversation_id: Conversation ID to delete.

        Raises:
            Error: If conversation not found or conversation is processing.
        """
        self._logger.debug("delete_started", conversation_id=str(conversation_id))

        async with self._database.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if not conversation:
                raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

            if conversation.processing:
                raise Error(ErrorCode.NOT_ALLOWED, "Cannot delete conversation while processing")

            await session.delete(conversation)
            await session.commit()

        self._logger.debug("delete_completed", conversation_id=str(conversation_id))

        self.bus.notify_deleted(conversation_id)

    @handle_database_errors
    async def split(self, split_at_message_id: UUID) -> Conversation:
        """Split conversation at a specific message, creating a new conversation.

        Creates a new conversation with all messages from the beginning up to and
        including the specified message. The original conversation remains unchanged.

        Args:
            split_at_message_id: Message ID to split at (included in new conversation).

        Returns:
            Newly created conversation with copied messages.

        Raises:
            Error: If message not found.
        """
        self._logger.debug("split_started", split_at_message_id=str(split_at_message_id))

        async with self._database.session() as session:
            split_message = await session.get(Message, split_at_message_id)
            if not split_message:
                raise Error(ErrorCode.NOT_FOUND, "Message not found")

            original_conversation = await session.get(Conversation, split_message.conversation_id)
            if not original_conversation:
                raise Error(ErrorCode.NOT_FOUND, "Conversation not found")

            new_conversation = Conversation(
                name=original_conversation.name,
                agent_id=original_conversation.agent_id,
                processing=False,
                error_code=None,
                error_message=None,
            )
            session.add(new_conversation)
            await session.flush()

            result = await session.execute(
                select(Message)
                .where(column("conversation_id") == split_message.conversation_id)
                .where(column("sequence") <= split_message.sequence)
                .order_by(column("sequence"))
            )
            messages_to_copy = result.scalars().all()

            for message in messages_to_copy:
                new_message = Message(
                    content=message.content,
                    sequence=message.sequence,
                    conversation_id=new_conversation.id,
                )
                session.add(new_message)

            await session.commit()
            await session.refresh(new_conversation)

        self._logger.debug(
            "split_completed",
            split_at_message_id=str(split_at_message_id),
            new_conversation_id=str(new_conversation.id),
            messages_copied=len(messages_to_copy),
        )

        self.bus.notify_save(new_conversation)

        return new_conversation
