import asyncio
from typing import AsyncIterator
from uuid import UUID
from ...common import Logger
from ...models import Message


class MessageBus:
    """Notification bus for message create, update, and delete_after events."""

    def __init__(self) -> None:
        self._save_queues: list[tuple[UUID | None, asyncio.Queue[Message]]] = []
        self._delete_after_queues: list[tuple[UUID, asyncio.Queue[UUID]]] = []
        self._logger = Logger.get_logger("database.buses.message_bus")

    def notify_save(self, message: Message) -> None:
        """Notify watchers of a message create or update.

        Args:
            message: The saved message.
        """
        for conversation_id, queue in self._save_queues:
            if conversation_id is None or conversation_id == message.conversation_id:
                queue.put_nowait(message)

    def notify_deleted_after(self, message_id: UUID, conversation_id: UUID) -> None:
        """Notify watchers that all messages after a specific message were deleted.

        Args:
            message_id: The anchor message ID — everything after this was deleted.
            conversation_id: The conversation ID the deletion applies to.
        """
        for conv_id, queue in self._delete_after_queues:
            if conv_id == conversation_id:
                queue.put_nowait(message_id)

    async def watch_saves(self, conversation_id: UUID | None = None) -> AsyncIterator[Message]:
        """Watch for message create and update events.

        Args:
            conversation_id: Optional ID to filter — None watches all conversations.

        Yields:
            Message on every save event matching the filter.
        """
        if conversation_id:
            self._logger.debug("watch_saves_started", conversation_id=str(conversation_id))
        else:
            self._logger.debug("watch_saves_started")

        queue: asyncio.Queue[Message] = asyncio.Queue()
        self._save_queues.append((conversation_id, queue))
        try:
            while True:
                yield await queue.get()
        finally:
            self._save_queues = [(conv_id, q) for conv_id, q in self._save_queues if q is not queue]
            if conversation_id:
                self._logger.debug("watch_saves_completed", conversation_id=str(conversation_id))
            else:
                self._logger.debug("watch_saves_completed")

    async def watch_delete_afters(self, conversation_id: UUID) -> AsyncIterator[UUID]:
        """Watch for delete_after events for a conversation.

        Args:
            conversation_id: Conversation ID to filter by.

        Yields:
            Anchor message ID — everything after this message was deleted.
        """
        self._logger.debug("watch_delete_afters_started", conversation_id=str(conversation_id))

        queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._delete_after_queues.append((conversation_id, queue))
        try:
            while True:
                yield await queue.get()
        finally:
            self._delete_after_queues = [
                (conv_id, q) for conv_id, q in self._delete_after_queues if q is not queue
            ]
            self._logger.debug(
                "watch_delete_afters_completed", conversation_id=str(conversation_id)
            )
