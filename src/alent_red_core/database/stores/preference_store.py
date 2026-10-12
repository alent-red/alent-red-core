from __future__ import annotations

from typing import TYPE_CHECKING
from sqlmodel import select
from ...common import Logger
from ...models import Error, ErrorCode, Preference, PreferenceInput, PreferenceKey
from ..utils import handle_database_errors

if TYPE_CHECKING:
    from ..database import Database


class PreferenceStore:
    """Manages preference storage operations."""

    def __init__(self, database: Database):
        """Initialize preference store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.preference_store")

    @handle_database_errors
    async def get_all(self) -> list[Preference]:
        """Fetch all preferences.

        Returns:
            List of all preferences.
        """
        self._logger.debug("get_all_started")

        async with self._database.session() as session:
            result = await session.execute(select(Preference))
            preferences = result.scalars().all()
            preference_list = list(preferences)

        self._logger.debug("get_all_completed", count=len(preference_list))

        return preference_list

    @handle_database_errors
    async def get(self, key: PreferenceKey) -> Preference | None:
        """Get preference by key.

        Args:
            key: Preference key to fetch.

        Returns:
            Preference if found, None otherwise.
        """
        self._logger.debug("get_started", key=key.value)

        async with self._database.session() as session:
            result = await session.execute(select(Preference).where(Preference.key == key))
            preference = result.scalar_one_or_none()

        self._logger.debug("get_completed", key=key.value, found=preference is not None)

        return preference

    @handle_database_errors
    async def save_many(
        self, preference_inputs: list[PreferenceInput], skip_existing: bool
    ) -> list[Preference]:
        """Save multiple preferences.

        Args:
            preference_inputs: List of preferences to save.
            skip_existing: If True, skip existing preferences (insert new only).
                          If False, upsert (insert new, update existing).

        Returns:
            List of saved preferences.
        """
        self._logger.debug(
            "save_many_started", count=len(preference_inputs), skip_existing=skip_existing
        )

        preferences: list[Preference] = []
        async with self._database.session() as session:
            for preference_input in preference_inputs:
                result = await session.execute(
                    select(Preference).where(Preference.key == preference_input.key)
                )
                existing_preference = result.scalar_one_or_none()

                if existing_preference:
                    if skip_existing:
                        continue
                    if existing_preference.value.type != preference_input.value.type:
                        raise Error(
                            ErrorCode.NOT_ALLOWED,
                            f"Cannot change preference type for key {preference_input.key.value}",
                        )
                    existing_preference.value = preference_input.value
                    preferences.append(existing_preference)
                else:
                    new_preference = Preference(
                        key=preference_input.key, value=preference_input.value
                    )
                    session.add(new_preference)
                    preferences.append(new_preference)

            await session.commit()
            for pref in preferences:
                await session.refresh(pref)

        self._logger.debug("save_many_completed", saved_count=len(preferences))

        return preferences
