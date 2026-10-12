from ..database import Database
from ..blob import BlobStorage
from .looper import Looper


class LooperBuilder:
    """Factory for building looper instance."""

    @staticmethod
    async def build(database: Database, blob: BlobStorage) -> Looper:
        """Build and initialize looper.

        Args:
            database: Database instance.
            blob: Blob storage instance.

        Returns:
            Initialized and setup looper instance.
        """
        looper = Looper(database, blob)
        await looper.setup()
        return looper
