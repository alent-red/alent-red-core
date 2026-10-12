from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from sqlmodel import select
from ...common import Logger
from ...models import Provider, ProviderConfigType, ProviderInput, Error, ErrorCode
from ..utils import handle_database_errors

if TYPE_CHECKING:
    from ..database import Database


class ProviderStore:
    """Manages provider storage operations."""

    def __init__(self, database: Database):
        """Initialize provider store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.provider_store")

    @handle_database_errors
    async def get_all(self) -> list[Provider]:
        """Fetch all providers.

        Returns:
            List of all providers.
        """
        self._logger.debug("get_all_started")

        async with self._database.session() as session:
            result = await session.execute(select(Provider))
            providers = result.scalars().all()
            provider_list = list(providers)

        self._logger.debug("get_all_completed", count=len(provider_list))

        return provider_list

    @handle_database_errors
    async def get(self, provider_id: UUID) -> Provider | None:
        """Get provider by ID.

        Args:
            provider_id: Provider ID to fetch.

        Returns:
            Provider if found, None otherwise.
        """
        self._logger.debug("get_started", provider_id=str(provider_id))

        async with self._database.session() as session:
            result = await session.execute(select(Provider).where(Provider.id == provider_id))
            provider = result.scalar_one_or_none()

        self._logger.debug(
            "get_completed", provider_id=str(provider_id), found=provider is not None
        )

        return provider

    @handle_database_errors
    async def save(self, provider_input: ProviderInput, provider_id: UUID | None) -> Provider:
        """Save provider (create new or update existing).

        Args:
            provider_input: Provider data to save.
            provider_id: Provider ID to update (None for new provider).

        Returns:
            Saved provider.

        Raises:
            Error: If provider not found (update mode).
        """
        if provider_id:
            self._logger.debug("save_started", provider_id=str(provider_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if provider_id:
                result = await session.execute(select(Provider).where(Provider.id == provider_id))
                existing_provider = result.scalar_one_or_none()

                if not existing_provider:
                    raise Error(ErrorCode.NOT_FOUND, "Provider not found")

                if existing_provider.config.type != provider_input.config.type:
                    raise Error(
                        ErrorCode.NOT_ALLOWED,
                        "Cannot change provider config type",
                    )

                existing_provider.name = provider_input.name
                existing_provider.config = provider_input.config
                provider = existing_provider
            else:
                new_provider = Provider(name=provider_input.name, config=provider_input.config)
                session.add(new_provider)
                provider = new_provider

            await session.commit()
            await session.refresh(provider)

        if provider_id:
            self._logger.debug("save_completed", provider_id=str(provider.id), mode="update")
        else:
            self._logger.debug("save_completed", provider_id=str(provider.id), mode="create")

        return provider

    @handle_database_errors
    async def delete(self, provider_id: UUID) -> None:
        """Delete provider by ID.

        Args:
            provider_id: Provider ID to delete.

        Raises:
            Error: If provider not found.
        """
        self._logger.debug("delete_started", provider_id=str(provider_id))

        async with self._database.session() as session:
            result = await session.execute(select(Provider).where(Provider.id == provider_id))
            provider = result.scalar_one_or_none()

            if not provider:
                raise Error(ErrorCode.NOT_FOUND, "Provider not found")

            await session.delete(provider)

        self._logger.debug("delete_completed", provider_id=str(provider_id))
