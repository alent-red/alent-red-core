from uuid import UUID
from typing import TYPE_CHECKING

from ..common import Logger
from ..models import (
    Conversation,
    Error,
    ErrorCode,
    MessageContentToolResponse,
    PreferenceKey,
    PreferenceValueType,
    Tool,
)
from ..database import Database
from ..blob import BlobStorage
from .base_brick import BaseBrick
from .brick_builder import BrickBuilder

if TYPE_CHECKING:
    from ..looper import Looper
    from ..providers import ProviderManager


class BrickManager:
    """Manages lifecycle and orchestration of all brick instances."""

    def __init__(
        self,
        looper: "Looper",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize brick manager.

        Args:
            looper: Looper instance for triggering conversation processing.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        self._looper = looper
        self._providers = providers
        self._database = database
        self._blob = blob
        self.bricks: dict[UUID, BaseBrick] = {}
        self._tool_separator: str = ""
        self._prompt_separator: str = ""
        self._logger = Logger.get_logger("bricks.brick_manager")

    async def setup(self) -> None:
        """Setup the brick manager and initialize all bricks.

        Raises:
            Error: If required preferences are not found.
        """
        self._logger.debug("setup_started")

        await self._load_preferences()

        bricks = await self._database.bricks.get_all()
        for brick in bricks:
            brick_instance = await BrickBuilder.build(
                brick, self._looper, self, self._providers, self._database, self._blob
            )
            self.bricks[brick.id] = brick_instance

        self._logger.debug("setup_completed", count=len(self.bricks))

    async def refresh(self) -> None:
        """Refresh all bricks from database.

        Raises:
            Error: If required preferences are not found.
        """
        self._logger.debug("refresh_started")

        await self._load_preferences()

        bricks = await self._database.bricks.get_all()
        db_brick_ids = {brick.id for brick in bricks}
        current_brick_ids = set(self.bricks.keys())

        for brick in bricks:
            if brick.id in self.bricks:
                await self.bricks[brick.id].refresh(brick.config)
            else:
                brick_instance = await BrickBuilder.build(
                    brick, self._looper, self, self._providers, self._database, self._blob
                )
                self.bricks[brick.id] = brick_instance

        removed_brick_ids = current_brick_ids - db_brick_ids
        for brick_id in removed_brick_ids:
            await self.bricks[brick_id].clean()
            del self.bricks[brick_id]

        self._logger.debug(
            "refresh_completed",
            count=len(self.bricks),
            added=len(db_brick_ids - current_brick_ids),
            removed=len(removed_brick_ids),
        )

    async def clean(self) -> None:
        """Clean the brick manager and cleanup all bricks."""
        self._logger.debug("clean_started", count=len(self.bricks))

        for brick in self.bricks.values():
            await brick.clean()
        self.bricks.clear()

        self._logger.debug("clean_completed")

    async def before_loop(self, conversation: Conversation) -> None:
        """Call before_loop on all bricks.

        Args:
            conversation: Conversation object.
        """
        for brick in self.bricks.values():
            await brick.before_loop(conversation)

    async def after_loop(self, conversation: Conversation) -> None:
        """Call after_loop on all bricks.

        Args:
            conversation: Conversation object.
        """
        for brick in self.bricks.values():
            await brick.after_loop(conversation)

    async def get_prompt(self, conversation: Conversation) -> str | None:
        """Get aggregated prompt from all bricks.

        Args:
            conversation: Conversation object.

        Returns:
            Aggregated prompt or None.

        Raises:
            Error: If conversation has no agent or preference is invalid.
        """
        self._logger.debug("get_prompt_started", conversation_id=str(conversation.id))

        if conversation.agent_id is None:
            raise Error(ErrorCode.INVALID_ARGUMENT, "Conversation must have an agent")

        agent_bricks = await self._database.bricks.get_all(agent_id=conversation.agent_id)

        prompts = []
        for agent_brick in agent_bricks:
            if agent_brick.id in self.bricks:
                brick = self.bricks[agent_brick.id]
                prompt = await brick.get_prompt(conversation)
                if prompt is not None:
                    prompts.append(prompt)

        if not prompts:
            self._logger.debug(
                "get_prompt_completed", conversation_id=str(conversation.id), has_prompt=False
            )
            return None

        result = self._prompt_separator.join(prompts)
        self._logger.debug(
            "get_prompt_completed",
            conversation_id=str(conversation.id),
            has_prompt=True,
            prompt_count=len(prompts),
        )

        return result

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get aggregated tools from all bricks.

        Args:
            conversation: Conversation object.

        Returns:
            List of all tools or None.

        Raises:
            Error: If conversation has no agent or duplicate tool names found.
        """
        self._logger.debug("get_tools_started", conversation_id=str(conversation.id))

        if conversation.agent_id is None:
            raise Error(ErrorCode.INVALID_ARGUMENT, "Conversation must have an agent")

        agent_bricks = await self._database.bricks.get_all(agent_id=conversation.agent_id)

        tools = []
        seen_tool_names: set[str] = set()

        for agent_brick in agent_bricks:
            if agent_brick.id in self.bricks:
                brick = self.bricks[agent_brick.id]
                brick_tools = await brick.get_tools(conversation)
                if brick_tools is not None:
                    identifier = await brick.get_identifier()
                    if self._tool_separator in identifier:
                        raise Error(
                            ErrorCode.INVALID_RESPONSE,
                            f"Brick identifier cannot contain tool separator: {identifier}",
                        )
                    for tool in brick_tools:
                        prefixed_name = f"{identifier}{self._tool_separator}{tool.name}"
                        if prefixed_name in seen_tool_names:
                            raise Error(
                                ErrorCode.INVALID_RESPONSE,
                                f"Duplicate tool name found: {prefixed_name}",
                            )
                        seen_tool_names.add(prefixed_name)
                        prefixed_tool = Tool(
                            name=prefixed_name,
                            description=tool.description,
                            parameters_schema=tool.parameters_schema,
                        )
                        tools.append(prefixed_tool)

        if not tools:
            self._logger.debug(
                "get_tools_completed", conversation_id=str(conversation.id), has_tools=False
            )
            return None

        self._logger.debug(
            "get_tools_completed",
            conversation_id=str(conversation.id),
            has_tools=True,
            tool_count=len(tools),
        )

        return tools

    async def handle_tool_request(
        self,
        name: str,
        parameters: str,
        conversation: Conversation,
    ) -> MessageContentToolResponse | None:
        """Route tool request to appropriate brick.

        Args:
            name: Tool name (prefixed with brick identifier).
            parameters: Tool parameters as JSON string.
            conversation: Conversation object.

        Returns:
            Tool response or None.

        Raises:
            Error: If conversation has no agent or tool not found.
        """
        self._logger.debug(
            "handle_tool_request_started",
            conversation_id=str(conversation.id),
            tool_name=name,
        )

        if conversation.agent_id is None:
            raise Error(ErrorCode.INVALID_ARGUMENT, "Conversation must have an agent")

        if self._tool_separator not in name:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Invalid tool name format: {name}")

        identifier, tool_name = name.split(self._tool_separator, 1)

        agent_bricks = await self._database.bricks.get_all(agent_id=conversation.agent_id)

        for agent_brick in agent_bricks:
            if agent_brick.id in self.bricks:
                brick = self.bricks[agent_brick.id]
                brick_identifier = await brick.get_identifier()
                if brick_identifier == identifier:
                    response = await brick.handle_tool_request(tool_name, parameters, conversation)
                    if response is None:
                        raise Error(
                            ErrorCode.INVALID_RESPONSE,
                            f"Tool {tool_name} returned None in brick {identifier}",
                        )
                    self._logger.debug(
                        "handle_tool_request_completed",
                        conversation_id=str(conversation.id),
                        tool_name=name,
                        brick_identifier=identifier,
                    )
                    return response

        raise Error(ErrorCode.NOT_FOUND, f"Brick with identifier {identifier} not found")

    async def _load_preferences(self) -> None:
        """Load required preferences from database.

        Raises:
            Error: If required preferences are not found or have invalid types.
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

        prompt_separator_preference = await self._database.preferences.get(
            PreferenceKey.BRICK_PROMPT_SEPARATOR
        )
        if prompt_separator_preference is None:
            raise Error(
                ErrorCode.NOT_FOUND,
                f"Required preference {PreferenceKey.BRICK_PROMPT_SEPARATOR} not found",
            )
        if prompt_separator_preference.value.type != PreferenceValueType.STRING:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Preference {PreferenceKey.BRICK_PROMPT_SEPARATOR} must be string type",
            )
        self._prompt_separator = prompt_separator_preference.value.value
