from ..database import Database
from ..blob import BlobStorage
from ..looper import Looper
from .gateway_manager import GatewayManager


class GatewayManagerBuilder:
    """Factory for building gateway manager instance."""

    @staticmethod
    async def build(looper: Looper, database: Database, blob: BlobStorage) -> GatewayManager:
        """Build and initialize gateway manager.

        Args:
            looper: Looper instance for triggering conversation processing.
            database: Database instance.
            blob: Blob storage instance.

        Returns:
            Initialized and setup gateway manager instance.
        """
        manager = GatewayManager(looper, database, blob)
        await manager.setup()
        return manager
