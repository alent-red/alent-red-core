import asyncio
import datetime
import json
from uuid import UUID, uuid4
from typing import TYPE_CHECKING

from ..base_brick import BaseBrick
from ...common import Logger
from ...models import (
    BrickConfigScheduler,
    Conversation,
    Error,
    ErrorCode,
    MessageContentInternal,
    MessageContentToolResponse,
    MessageInput,
    Tool,
)
from ...database import Database
from ...blob import BlobStorage

if TYPE_CHECKING:
    from ..brick_manager import BrickManager
    from ...looper import Looper
    from ...providers import ProviderManager


class ScheduledNotification:
    """Single in-memory scheduled notification entry."""

    def __init__(
        self,
        notification_id: UUID,
        conversation_id: UUID,
        prompt: str,
        fire_at: datetime.datetime,
        task: asyncio.Task[None],
    ):
        """Initialize scheduled notification.

        Args:
            notification_id: Unique notification identifier.
            conversation_id: Owning conversation identifier.
            prompt: Reminder text to deliver to the LLM when it fires.
            fire_at: Local-timezone-aware datetime to fire at.
            task: Backing asyncio task that sleeps until fire_at.
        """
        self.notification_id = notification_id
        self.conversation_id = conversation_id
        self.prompt = prompt
        self.fire_at = fire_at
        self.task = task


class SchedulerBrick(BaseBrick):
    """Scheduler brick allowing the LLM to schedule deferred self-notifications."""

    _identifier = "scheduler"

    _tool_schedule_notification = "schedule_notification"
    _tool_list_scheduled_notifications = "list_scheduled_notifications"
    _tool_delete_scheduled_notification = "delete_scheduled_notification"
    _tool_wait = "wait"

    _internal_message_template = "Scheduled notification {{ID}} at {{TIME}}: {{PROMPT}}"
    _time_format = "%Y-%m-%dT%H:%M:%S"

    def __init__(
        self,
        config: BrickConfigScheduler,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize scheduler brick.

        Args:
            config: Scheduler brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        super().__init__(config, looper, bricks, providers, database, blob)
        self._logger = Logger.get_logger("bricks.scheduler.scheduler_brick")
        self._notifications: dict[UUID, ScheduledNotification] = {}
        self._deletion_watcher_task: asyncio.Task[None] | None = None

    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        return self._identifier

    async def setup(self) -> None:
        """Start the conversation-deletion watcher."""
        self._logger.debug("setup_started")
        self._deletion_watcher_task = asyncio.create_task(self._watch_conversation_deletions())
        self._logger.debug("setup_completed")

    async def clean(self) -> None:
        """Cancel all scheduled notifications and the deletion watcher."""
        self._logger.debug("clean_started", notification_count=len(self._notifications))

        for notification in list(self._notifications.values()):
            notification.task.cancel()
        await asyncio.gather(
            *(notification.task for notification in self._notifications.values()),
            return_exceptions=True,
        )
        self._notifications.clear()

        if self._deletion_watcher_task is not None:
            self._deletion_watcher_task.cancel()
            await asyncio.gather(self._deletion_watcher_task, return_exceptions=True)
            self._deletion_watcher_task = None

        self._logger.debug("clean_completed")

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick.

        Args:
            conversation: Conversation object.

        Returns:
            List of tools.
        """
        self._logger.debug("get_tools_started", conversation_id=str(conversation.id))

        tools = [
            Tool(
                name=self._tool_schedule_notification,
                description=(
                    "Schedule a deferred notification that will arrive back as an internal "
                    "message in this conversation at the given local time. You must check "
                    "the current time before setting it when user asks relative. Each "
                    "notification fires. exactly once. For recurring schedules you need to "
                    "reschedule the next one after firing the first one. Include "
                    "instructions in description to remember that."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": (
                                "Reminder text delivered back to you when the notification fires."
                            ),
                        },
                        "time": {
                            "type": "string",
                            "description": (
                                "Naive ISO 8601 local datetime, e.g. '2026-05-23T14:30:00'. "
                                "Must be in the future. Timezone suffixes are rejected."
                            ),
                        },
                    },
                    "required": ["prompt", "time"],
                },
            ),
            Tool(
                name=self._tool_list_scheduled_notifications,
                description=(
                    "List all pending scheduled notifications for this conversation as an "
                    "array of {id, prompt, time} entries."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name=self._tool_delete_scheduled_notification,
                description=(
                    "Cancel a pending scheduled notification for this conversation by id."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Notification id returned by schedule_notification.",
                        },
                    },
                    "required": ["id"],
                },
            ),
            Tool(
                name=self._tool_wait,
                description=(
                    "Wait for N seconds. Useful for short polls (e.g. wait 5s then check "
                    "status). Returns confirmation and the new current time."
                ),
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "seconds": {
                            "type": "integer",
                            "description": "Number of seconds to wait.",
                            "minimum": 1,
                        },
                    },
                    "required": ["seconds"],
                },
            ),
        ]

        self._logger.debug(
            "get_tools_completed",
            conversation_id=str(conversation.id),
            tool_count=len(tools),
        )

        return tools

    async def handle_tool_request(
        self,
        name: str,
        parameters: str,
        conversation: Conversation,
    ) -> MessageContentToolResponse | None:
        """Handle tool request.

        Args:
            name: Tool name.
            parameters: Tool parameters as JSON string.
            conversation: Conversation object.

        Returns:
            Tool response.

        Raises:
            Error: If tool name is unknown or parameters are invalid.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        try:
            parsed_parameters = json.loads(parameters)
        except json.JSONDecodeError as exception:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid JSON parameters: {exception}",
            )

        if not isinstance(parsed_parameters, dict):
            raise Error(ErrorCode.INVALID_ARGUMENT, "Parameters must be a JSON object")

        if name == self._tool_schedule_notification:
            response = await self._handle_schedule_notification(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_list_scheduled_notifications:
            response = await self._handle_list_scheduled_notifications(conversation=conversation)
        elif name == self._tool_delete_scheduled_notification:
            response = await self._handle_delete_scheduled_notification(
                parameters=parsed_parameters, conversation=conversation
            )
        elif name == self._tool_wait:
            response = await self._handle_wait(
                parameters=parsed_parameters, conversation=conversation
            )
        else:
            raise Error(ErrorCode.NOT_FOUND, f"Unknown tool: {name}")

        self._logger.debug(
            "handle_tool_request_completed",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        return response

    async def _handle_schedule_notification(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Register a new scheduled notification.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response containing the new notification id.

        Raises:
            Error: If parameters are invalid or the time is in the past.
        """
        self._logger.info("schedule_notification_started", conversation_id=str(conversation.id))

        prompt = self._read_prompt(parameters=parameters)
        fire_at = self._read_time(parameters=parameters)

        now = datetime.datetime.now().astimezone()
        if fire_at <= now:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Scheduled time must be in the future (now is {now.strftime(self._time_format)})",
            )

        notification_id = uuid4()
        delay_seconds = (fire_at - now).total_seconds()

        task = asyncio.create_task(
            self._fire_after_delay(
                notification_id=notification_id,
                conversation_id=conversation.id,
                prompt=prompt,
                fire_at=fire_at,
                delay_seconds=delay_seconds,
            )
        )

        self._notifications[notification_id] = ScheduledNotification(
            notification_id=notification_id,
            conversation_id=conversation.id,
            prompt=prompt,
            fire_at=fire_at,
            task=task,
        )

        self._logger.info(
            "schedule_notification_completed",
            conversation_id=str(conversation.id),
            notification_id=str(notification_id),
            fire_at=fire_at.strftime(self._time_format),
            delay_seconds=delay_seconds,
        )

        payload = {"id": str(notification_id)}
        return MessageContentToolResponse(text=json.dumps(payload))

    async def _handle_list_scheduled_notifications(
        self, conversation: Conversation
    ) -> MessageContentToolResponse:
        """Return the conversation's pending scheduled notifications.

        Args:
            conversation: Conversation object.

        Returns:
            Tool response with the list of {id, prompt, time} entries.
        """
        self._logger.debug(
            "list_scheduled_notifications_started", conversation_id=str(conversation.id)
        )

        entries = [
            {
                "id": str(notification.notification_id),
                "prompt": notification.prompt,
                "time": notification.fire_at.strftime(self._time_format),
            }
            for notification in self._notifications.values()
            if notification.conversation_id == conversation.id
        ]

        self._logger.debug(
            "list_scheduled_notifications_completed",
            conversation_id=str(conversation.id),
            count=len(entries),
        )

        return MessageContentToolResponse(text=json.dumps(entries))

    async def _handle_delete_scheduled_notification(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Cancel a pending scheduled notification.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response confirming the deletion.

        Raises:
            Error: If parameters are invalid or the notification is not
                found in this conversation.
        """
        self._logger.info(
            "delete_scheduled_notification_started", conversation_id=str(conversation.id)
        )

        notification_id = self._read_notification_id(parameters=parameters)

        notification = self._notifications.get(notification_id)
        if notification is None or notification.conversation_id != conversation.id:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Scheduled notification not found: {notification_id}",
            )

        notification.task.cancel()
        del self._notifications[notification_id]

        self._logger.info(
            "delete_scheduled_notification_completed",
            conversation_id=str(conversation.id),
            notification_id=str(notification_id),
        )

        payload = {"id": str(notification_id), "deleted": True}
        return MessageContentToolResponse(text=json.dumps(payload))

    async def _handle_wait(
        self, parameters: dict[str, object], conversation: Conversation
    ) -> MessageContentToolResponse:
        """Suspend this conversation for N seconds then return the new now.

        Args:
            parameters: Parsed tool parameters.
            conversation: Conversation object.

        Returns:
            Tool response containing waited_seconds and the new current time.

        Raises:
            Error: If parameters are invalid.
        """
        seconds = self._read_seconds(parameters=parameters)

        self._logger.info(
            "wait_started",
            conversation_id=str(conversation.id),
            seconds=seconds,
        )

        await asyncio.sleep(seconds)

        now = datetime.datetime.now().astimezone()
        payload = {
            "waited_seconds": seconds,
            "now": now.strftime(self._time_format),
        }

        self._logger.info(
            "wait_completed",
            conversation_id=str(conversation.id),
            seconds=seconds,
        )

        return MessageContentToolResponse(text=json.dumps(payload))

    def _read_prompt(self, parameters: dict[str, object]) -> str:
        raw_prompt = parameters.get("prompt")
        if not isinstance(raw_prompt, str) or not raw_prompt.strip():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: prompt",
            )
        return raw_prompt.strip()

    def _read_time(self, parameters: dict[str, object]) -> datetime.datetime:
        raw_time = parameters.get("time")
        if not isinstance(raw_time, str) or not raw_time.strip():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: time",
            )

        time_value = raw_time.strip()
        try:
            parsed = datetime.datetime.fromisoformat(time_value)
        except ValueError as exception:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid ISO 8601 time: {exception}",
            )

        if parsed.tzinfo is not None:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Time must be naive ISO 8601 without a timezone suffix",
            )

        local_tzinfo = datetime.datetime.now().astimezone().tzinfo
        return parsed.replace(tzinfo=local_tzinfo)

    def _read_notification_id(self, parameters: dict[str, object]) -> UUID:
        raw_id = parameters.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: id",
            )

        try:
            return UUID(raw_id.strip())
        except ValueError as exception:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Invalid notification id: {exception}",
            )

    def _read_seconds(self, parameters: dict[str, object]) -> int:
        raw_seconds = parameters.get("seconds")
        if not isinstance(raw_seconds, int) or isinstance(raw_seconds, bool) or raw_seconds < 1:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                "Missing or invalid required parameter: seconds",
            )
        return raw_seconds

    async def _fire_after_delay(
        self,
        notification_id: UUID,
        conversation_id: UUID,
        prompt: str,
        fire_at: datetime.datetime,
        delay_seconds: float,
    ) -> None:
        """Sleep until fire_at, then deliver the notification.

        Args:
            notification_id: Notification identifier.
            conversation_id: Owning conversation identifier.
            prompt: Reminder text.
            fire_at: Scheduled fire datetime (local tz aware).
            delay_seconds: Seconds to sleep before firing.
        """
        try:
            await asyncio.sleep(delay_seconds)
            await self._deliver_notification(
                notification_id=notification_id,
                conversation_id=conversation_id,
                prompt=prompt,
                fire_at=fire_at,
            )
        except asyncio.CancelledError:
            self._logger.debug(
                "fire_after_delay_cancelled",
                notification_id=str(notification_id),
                conversation_id=str(conversation_id),
            )
            raise
        except Exception as exception:
            self._logger.warning(
                "fire_after_delay_failed",
                notification_id=str(notification_id),
                conversation_id=str(conversation_id),
                error=str(exception),
            )
        finally:
            self._notifications.pop(notification_id, None)

    async def _deliver_notification(
        self,
        notification_id: UUID,
        conversation_id: UUID,
        prompt: str,
        fire_at: datetime.datetime,
    ) -> None:
        """Insert the internal message and trigger conversation processing.

        Args:
            notification_id: Notification identifier.
            conversation_id: Owning conversation identifier.
            prompt: Reminder text.
            fire_at: Scheduled fire datetime (local tz aware).

        Raises:
            Error: If the conversation has been deleted.
        """
        self._logger.info(
            "deliver_notification_started",
            notification_id=str(notification_id),
            conversation_id=str(conversation_id),
        )

        conversation = await self._database.conversations.get(conversation_id=conversation_id)
        if conversation is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Conversation {conversation_id} no longer exists",
            )

        text = (
            self._internal_message_template.replace("{{ID}}", str(notification_id))
            .replace("{{TIME}}", fire_at.strftime(self._time_format))
            .replace("{{PROMPT}}", prompt)
        )

        await self._database.messages.save(
            MessageInput(
                content=MessageContentInternal(text=text),
                conversation_id=conversation_id,
            ),
            None,
        )

        self._logger.info(
            "deliver_notification_completed",
            notification_id=str(notification_id),
            conversation_id=str(conversation_id),
        )

        await self._looper.process(conversation)

    async def _watch_conversation_deletions(self) -> None:
        """Cancel notifications whose conversation is deleted."""
        try:
            async for conversation_id in self._database.conversations.bus.watch_deletions():
                self._cancel_notifications_for_conversation(conversation_id=conversation_id)
        except asyncio.CancelledError:
            raise
        except Exception as exception:
            self._logger.warning("watch_conversation_deletions_failed", error=str(exception))

    def _cancel_notifications_for_conversation(self, conversation_id: UUID) -> None:
        """Cancel and drop all notifications belonging to a deleted conversation.

        Args:
            conversation_id: Deleted conversation identifier.
        """
        affected = [
            notification
            for notification in self._notifications.values()
            if notification.conversation_id == conversation_id
        ]
        for notification in affected:
            notification.task.cancel()
            self._notifications.pop(notification.notification_id, None)

        if affected:
            self._logger.info(
                "cancel_notifications_for_conversation_completed",
                conversation_id=str(conversation_id),
                count=len(affected),
            )
