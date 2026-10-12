from typing import TYPE_CHECKING

from ..models import Brick, BrickConfigType, Error, ErrorCode
from ..database import Database
from ..blob import BlobStorage
from .base_brick import BaseBrick
from .code import CodeBrick
from .scheduler import SchedulerBrick
from .system import SystemBrick
from .ui import UIBrick
from .vision import VisionBrick
from .skills import SkillsBrick

if TYPE_CHECKING:
    from .brick_manager import BrickManager
    from ..looper import Looper
    from ..providers import ProviderManager


class BrickBuilder:
    """Factory for building brick instances."""

    @staticmethod
    async def build(
        brick: Brick,
        looper: "Looper",
        bricks: "BrickManager",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ) -> BaseBrick:
        """Build brick instance for specified brick configuration.

        Args:
            brick: Brick configuration from database.
            looper: Looper instance for triggering conversation processing.
            bricks: Brick manager instance.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.

        Returns:
            Initialized and setup brick instance.

        Raises:
            Error: If brick type is not supported.
        """
        config = brick.config
        instance: BaseBrick

        if config.type == BrickConfigType.UI:
            instance = UIBrick(config, looper, bricks, providers, database, blob)
            await instance.setup()
            return instance
        elif config.type == BrickConfigType.CODE:
            instance = CodeBrick(config, looper, bricks, providers, database, blob)
            await instance.setup()
            return instance
        elif config.type == BrickConfigType.VISION:
            instance = VisionBrick(config, looper, bricks, providers, database, blob)
            await instance.setup()
            return instance
        elif config.type == BrickConfigType.SKILLS:
            instance = SkillsBrick(config, looper, bricks, providers, database, blob)
            await instance.setup()
            return instance
        elif config.type == BrickConfigType.CUSTOM:
            raise Error(ErrorCode.NOT_SUPPORTED, "Custom brick not yet implemented")
        elif config.type == BrickConfigType.SYSTEM:
            instance = SystemBrick(config, looper, bricks, providers, database, blob)
            await instance.setup()
            return instance
        elif config.type == BrickConfigType.SCHEDULER:
            instance = SchedulerBrick(config, looper, bricks, providers, database, blob)
            await instance.setup()
            return instance
        elif config.type == BrickConfigType.RENDERER:
            raise Error(ErrorCode.NOT_SUPPORTED, "Renderer brick not yet implemented")
        elif config.type == BrickConfigType.BROWSER:
            raise Error(ErrorCode.NOT_SUPPORTED, "Browser brick not yet implemented")
        elif config.type == BrickConfigType.AGENT:
            raise Error(ErrorCode.NOT_SUPPORTED, "Agent brick not yet implemented")
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported brick type: {config.type}")
