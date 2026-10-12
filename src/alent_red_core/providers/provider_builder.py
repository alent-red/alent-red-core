from ..models import Provider
from ..database import Database
from .base_provider import BaseProvider
from .implementations import CommonProvider


class ProviderBuilder:
    """Factory for building provider instances."""

    @staticmethod
    async def build(provider: Provider, database: Database) -> BaseProvider:
        """Build provider instance for specified provider configuration.

        Args:
            provider: Provider configuration from database.
            database: Database instance.

        Returns:
            Initialized and setup provider instance.
        """
        instance: BaseProvider = CommonProvider(provider.config, database)
        await instance.setup()
        return instance
