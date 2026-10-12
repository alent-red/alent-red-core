from typing import TYPE_CHECKING

from ..database import Database
from ..blob import BlobStorage
from .brick_manager import BrickManager

if TYPE_CHECKING:
    from ..looper import Looper
    from ..providers import ProviderManager


class BrickManagerBuilder:
    """Factory for building brick manager instance."""

    @staticmethod
    async def build(
        looper: "Looper",
        providers: "ProviderManager",
        database: Database,
        blob: BlobStorage,
    ) -> BrickManager:
        """Build and initialize brick manager.

        Args:
            looper: Looper instance for triggering conversation processing.
            providers: Provider manager instance.
            database: Database instance.
            blob: Blob storage instance.

        Returns:
            Initialized and setup brick manager instance.
        """
        manager = BrickManager(looper, providers, database, blob)
        await manager.setup()
        return manager
