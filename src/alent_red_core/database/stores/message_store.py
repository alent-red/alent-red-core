from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import select, column, desc, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ...common import Logger
from ...models import Message, MessageInput, Error, ErrorCode
from ..utils import handle_database_errors
from ..buses import MessageBus

if TYPE_CHECKING:
    from ..database import Database


class MessageStore:
    """Manages message storage operations."""

    def __init__(self, database: Database):
        """Initialize message store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.message_store")
        self.bus = MessageBus()

    @handle_database_errors
    async def get_all(
        self,
        conversation_id: UUID,
        before_message_id: UUID | None = None,
        count: int | None = None,
    ) -> list[Message]:
        """Get messages for a conversation with pagination support.

        Args:
            conversation_id: Conversation ID to filter by.
            before_message_id: Optional message ID to paginate from (excluded).
            count: Optional maximum number of messages to return.

        Returns:
            List of messages in chronological order (oldest first).
        """
        if before_message_id:
            self._logger.debug(
                "get_all_started",
                conversation_id=str(conversation_id),
                before_message_id=str(before_message_id),
                count=count,
            )
        else:
            self._logger.debug("get_all_started", conversation_id=str(conversation_id), count=count)

        async with self._database.session() as session:
            query = select(Message).where(column("conversation_id") == conversation_id)

            if before_message_id:
                before_message = await session.get(Message, before_message_id)
                if not before_message:
                    raise Error(ErrorCode.NOT_FOUND, "Message not found")
                query = query.where(column("sequence") < before_message.sequence)

            query = query.order_by(desc(column("sequence")))

            if count:
                query = query.limit(count)

            result = await session.execute(query)
            messages = list(reversed(result.scalars().all()))

        if before_message_id:
            self._logger.debug(
                "get_all_completed",
                count=len(messages),
                conversation_id=str(conversation_id),
                before_message_id=str(before_message_id),
            )
        else:
            self._logger.debug(
                "get_all_completed", count=len(messages), conversation_id=str(conversation_id)
            )

        return messages

    @handle_database_errors
    async def save(self, message_input: MessageInput, message_id: UUID | None) -> Message:
        """Save message (create new or update existing).

        Args:
            message_input: Message data to save.
            message_id: Message ID to update (None for new message).

        Returns:
            Saved message.

        Raises:
            Error: If message not found (update mode) or foreign key violation.
        """
        if message_id:
            self._logger.debug("save_started", message_id=str(message_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if message_id:
                message = await session.get(Message, message_id)
                if not message:
                    raise Error(ErrorCode.NOT_FOUND, "Message not found")

                message.content = message_input.content
                message.conversation_id = message_input.conversation_id
                await session.commit()
                await session.refresh(message)
            else:
                message = await self._insert_with_sequence(
                    session=session, message_input=message_input
                )

        if message_id:
            self._logger.debug("save_completed", message_id=str(message.id), mode="update")
        else:
            self._logger.debug("save_completed", message_id=str(message.id), mode="create")

        self.bus.notify_save(message)

        return message

    async def _insert_with_sequence(
        self, session: AsyncSession, message_input: MessageInput
    ) -> Message:
        """Insert message with next per-conversation sequence; retry on UNIQUE collision.

        Args:
            session: Active async session.
            message_input: Message data to insert.

        Returns:
            Inserted message with assigned sequence.
        """
        while True:
            current_max_sequence = await session.scalar(
                select(func.max(Message.sequence)).where(
                    column("conversation_id") == message_input.conversation_id
                )
            )
            next_sequence = 1 if current_max_sequence is None else current_max_sequence + 1

            message = Message(
                content=message_input.content,
                conversation_id=message_input.conversation_id,
                sequence=next_sequence,
            )
            session.add(message)

            try:
                await session.commit()
                await session.refresh(message)
                return message
            except IntegrityError as exception:
                error_message = str(exception.orig)
                if "unique_message_conversation_id_sequence" not in error_message:
                    raise
                await session.rollback()
                self._logger.debug(
                    "save_sequence_collision",
                    conversation_id=str(message_input.conversation_id),
                    attempted_sequence=next_sequence,
                )

    @handle_database_errors
    async def delete_after(self, message_id: UUID) -> None:
        """Delete all messages after a specific message in the same conversation.

        Args:
            message_id: Message ID after which all messages should be deleted.

        Raises:
            Error: If message not found.
        """
        self._logger.debug("delete_after_started", message_id=str(message_id))

        conversation_id: UUID
        async with self._database.session() as session:
            message = await session.get(Message, message_id)
            if not message:
                raise Error(ErrorCode.NOT_FOUND, "Message not found")

            conversation_id = message.conversation_id

            await session.execute(
                delete(Message).where(
                    (column("conversation_id") == message.conversation_id)
                    & (column("sequence") > message.sequence)
                )
            )
            await session.commit()

        self._logger.debug("delete_after_completed", message_id=str(message_id))

        self.bus.notify_deleted_after(message_id, conversation_id)
