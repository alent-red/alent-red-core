import asyncio
from typing import AsyncIterator
from uuid import UUID
from ...common import Logger
from ...models import Conversation


class ConversationBus:
    """Notification bus for conversation create, update, and delete events."""

    def __init__(self) -> None:
        self._save_queues: list[tuple[UUID | None, asyncio.Queue[Conversation]]] = []
        self._deletion_queues: list[asyncio.Queue[UUID]] = []
        self._logger = Logger.get_logger("database.buses.conversation_bus")

    def notify_save(self, conversation: Conversation) -> None:
        """Notify watchers of a conversation create or update.

        Args:
            conversation: The saved conversation.
        """
        for filter_id, queue in self._save_queues:
            if filter_id is None or filter_id == conversation.id:
                queue.put_nowait(conversation)

    def notify_deleted(self, conversation_id: UUID) -> None:
        """Notify watchers of a deleted conversation.

        Args:
            conversation_id: The deleted conversation ID.
        """
        for queue in self._deletion_queues:
            queue.put_nowait(conversation_id)

    async def watch_saves(self, conversation_id: UUID | None = None) -> AsyncIterator[Conversation]:
        """Watch for conversation create and update events.

        Args:
            conversation_id: Optional ID to filter — None watches all conversations.

        Yields:
            Conversation on every save event matching the filter.
        """
        if conversation_id:
            self._logger.debug("watch_saves_started", conversation_id=str(conversation_id))
        else:
            self._logger.debug("watch_saves_started")

        queue: asyncio.Queue[Conversation] = asyncio.Queue()
        self._save_queues.append((conversation_id, queue))
        try:
            while True:
                yield await queue.get()
        finally:
            self._save_queues = [
                (filter_id, q) for filter_id, q in self._save_queues if q is not queue
            ]
            if conversation_id:
                self._logger.debug("watch_saves_completed", conversation_id=str(conversation_id))
            else:
                self._logger.debug("watch_saves_completed")

    async def watch_deletions(self) -> AsyncIterator[UUID]:
        """Watch for conversation delete events.

        Yields:
            Conversation ID on every delete event.
        """
        self._logger.debug("watch_deletions_started")

        queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._deletion_queues.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._deletion_queues = [q for q in self._deletion_queues if q is not queue]
            self._logger.debug("watch_deletions_completed")
