from ..database import Database
from ..blob import BlobStorage
from .provider_manager import ProviderManager


class ProviderManagerBuilder:
    """Factory for building provider manager instance."""

    @staticmethod
    async def build(database: Database, blob: BlobStorage) -> ProviderManager:
        """Build and initialize provider manager.

        Args:
            database: Database instance.
            blob: Blob storage instance.

        Returns:
            Initialized and setup provider manager instance.
        """
        manager = ProviderManager(database, blob)
        await manager.setup()
        return manager
