from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models import BrickConfig, Conversation, MessageContentToolResponse, Tool
from ..database import Database
from ..blob import BlobStorage

if TYPE_CHECKING:
    from .brick_manager import BrickManager
    from ..looper import Looper
    from ..providers import ProviderManager


class BaseBrick(ABC):
    """Base class for all bricks.

    Bricks are global instances initialized once and used across conversations.
    """

    def __init__(
        self,
        config: BrickConfig,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ):
        """Initialize brick.

        Args:
            config: Brick configuration.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.
        """
        self._config = config
        self._looper = looper
        self._bricks = bricks
        self._providers = providers
        self._database = database
        self._blob = blob

    @abstractmethod
    async def get_identifier(self) -> str:
        """Get unique identifier for this brick type.

        Returns:
            Brick identifier string.
        """
        pass

    async def setup(self) -> None:
        """Setup brick resources. Override in subclasses if needed."""
        pass

    async def refresh(self, config: BrickConfig) -> None:
        """Refresh brick resources. Override in subclasses if needed.

        Args:
            config: Updated brick configuration.
        """
        self._config = config

    async def clean(self) -> None:
        """Clean brick resources. Override in subclasses if needed."""
        pass

    async def before_loop(self, conversation: Conversation) -> None:
        """Hook called before conversation loop. Override if needed.

        Args:
            conversation: Conversation object.
        """
        pass

    async def after_loop(self, conversation: Conversation) -> None:
        """Hook called after conversation loop. Override if needed.

        Args:
            conversation: Conversation object.
        """
        pass

    async def get_prompt(self, conversation: Conversation) -> str | None:
        """Get prompt for this brick. Override if needed.

        Args:
            conversation: Conversation object.

        Returns:
            Prompt or None.
        """
        return None

    async def get_tools(self, conversation: Conversation) -> list[Tool] | None:
        """Get available tools for this brick. Override if needed.

        Args:
            conversation: Conversation object.

        Returns:
            List of tools or None.
        """
        return None

    async def handle_tool_request(
        self,
        name: str,
        parameters: str,
        conversation: Conversation,
    ) -> MessageContentToolResponse | None:
        """Handle tool request. Override if brick provides tools.

        Args:
            name: Tool name.
            parameters: Tool parameters as JSON string.
            conversation: Conversation object.

        Returns:
            Tool response or None.
        """
        return None
