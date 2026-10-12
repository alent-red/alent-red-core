from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import select, column
from ...common import Logger
from ...models import Brick, BrickConfigType, BrickInput, AgentBrick, Error, ErrorCode
from ..utils import handle_database_errors

if TYPE_CHECKING:
    from ..database import Database
    from sqlalchemy.ext.asyncio import AsyncSession


class BrickStore:
    """Manages brick storage operations."""

    def __init__(self, database: Database):
        """Initialize brick store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.brick_store")

    @handle_database_errors
    async def get_all(self, agent_id: UUID | None = None) -> list[Brick]:
        """Fetch all bricks.

        Args:
            agent_id: Optional agent ID to filter by.

        Returns:
            List of all bricks, optionally filtered by agent.
        """
        if agent_id:
            self._logger.debug("get_all_started", agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_started")

        async with self._database.session() as session:
            if agent_id:
                query = select(Brick).join(AgentBrick).where(column("agent_id") == agent_id)
            else:
                query = select(Brick)

            result = await session.execute(query)
            bricks = list(result.scalars().all())

        if agent_id:
            self._logger.debug("get_all_completed", count=len(bricks), agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_completed", count=len(bricks))

        return bricks

    @handle_database_errors
    async def get(self, brick_id: UUID) -> Brick | None:
        """Get brick by ID.

        Args:
            brick_id: Brick ID to fetch.

        Returns:
            Brick if found, None otherwise.
        """
        self._logger.debug("get_started", brick_id=str(brick_id))

        async with self._database.session() as session:
            result = await session.execute(select(Brick).where(column("id") == brick_id))
            brick = result.scalar_one_or_none()

        self._logger.debug("get_completed", brick_id=str(brick_id), found=brick is not None)

        return brick

    @handle_database_errors
    async def save(self, brick_input: BrickInput, brick_id: UUID | None) -> Brick:
        """Save brick (create new or update existing).

        Args:
            brick_input: Brick data to save.
            brick_id: Brick ID to update (None for new brick).

        Returns:
            Saved brick.

        Raises:
            Error: If brick not found (update mode), config type changed (update mode),
                or a non-CUSTOM brick of the same type already exists (create mode).
        """
        if brick_id:
            self._logger.debug("save_started", brick_id=str(brick_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if brick_id:
                result = await session.execute(select(Brick).where(column("id") == brick_id))
                existing_brick = result.scalar_one_or_none()

                if not existing_brick:
                    raise Error(ErrorCode.NOT_FOUND, "Brick not found")

                if existing_brick.config.type != brick_input.config.type:
                    raise Error(
                        ErrorCode.NOT_ALLOWED,
                        "Cannot change brick config type",
                    )

                existing_brick.name = brick_input.name
                existing_brick.config = brick_input.config
                brick = existing_brick
            else:
                if brick_input.config.type != BrickConfigType.CUSTOM:
                    await self._ensure_no_existing_brick_of_type(
                        session=session, config_type=brick_input.config.type
                    )

                new_brick = Brick(name=brick_input.name, config=brick_input.config)
                session.add(new_brick)
                brick = new_brick

            await session.commit()
            await session.refresh(brick)

        if brick_id:
            self._logger.debug("save_completed", brick_id=str(brick.id), mode="update")
        else:
            self._logger.debug("save_completed", brick_id=str(brick.id), mode="create")

        return brick

    async def _ensure_no_existing_brick_of_type(
        self, session: AsyncSession, config_type: BrickConfigType
    ) -> None:
        """Verify no brick with the given non-CUSTOM config type already exists.

        Args:
            session: Active async session.
            config_type: Brick config type to check.

        Raises:
            Error: If a brick of the given type already exists.
        """
        result = await session.execute(select(Brick))
        bricks = result.scalars().all()
        for brick in bricks:
            if brick.config.type == config_type:
                raise Error(
                    ErrorCode.NOT_ALLOWED,
                    f"A {config_type.value} brick already exists",
                )

    @handle_database_errors
    async def delete(self, brick_id: UUID) -> None:
        """Delete brick by ID.

        Args:
            brick_id: Brick ID to delete.

        Raises:
            Error: If brick not found.
        """
        self._logger.debug("delete_started", brick_id=str(brick_id))

        async with self._database.session() as session:
            result = await session.execute(select(Brick).where(column("id") == brick_id))
            brick = result.scalar_one_or_none()

            if not brick:
                raise Error(ErrorCode.NOT_FOUND, "Brick not found")

            await session.delete(brick)

        self._logger.debug("delete_completed", brick_id=str(brick_id))
