from uuid import UUID
from sqlalchemy import select, column
from typing import TYPE_CHECKING

from ...common import Logger
from ...models import Gateway, GatewayInput, Error, ErrorCode
from ..utils import handle_database_errors

if TYPE_CHECKING:
    from ..database import Database


class GatewayStore:
    """Manages gateway storage operations."""

    def __init__(self, database: "Database"):
        """Initialize gateway store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.gateway_store")

    @handle_database_errors
    async def get_all(self, agent_id: UUID | None = None) -> list[Gateway]:
        """Get all gateways.

        Args:
            agent_id: Optional agent ID to filter by.

        Returns:
            List of all gateways, optionally filtered by agent.
        """
        if agent_id:
            self._logger.debug("get_all_started", agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_started")

        async with self._database.session() as session:
            if agent_id:
                result = await session.execute(
                    select(Gateway).where(column("agent_id") == agent_id)
                )
            else:
                result = await session.execute(select(Gateway))
            gateways = list(result.scalars().all())

        if agent_id:
            self._logger.debug("get_all_completed", count=len(gateways), agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_completed", count=len(gateways))
        return gateways

    @handle_database_errors
    async def get(self, gateway_id: UUID) -> Gateway | None:
        """Get gateway by ID.

        Args:
            gateway_id: Gateway ID.

        Returns:
            Gateway if found, None otherwise.
        """
        self._logger.debug("get_started", gateway_id=str(gateway_id))

        async with self._database.session() as session:
            gateway = await session.get(Gateway, gateway_id)

        found = gateway is not None
        self._logger.debug("get_completed", gateway_id=str(gateway_id), found=found)
        return gateway

    @handle_database_errors
    async def save(self, gateway_input: GatewayInput, gateway_id: UUID | None = None) -> Gateway:
        """Save gateway (create or update).

        Args:
            gateway_input: Gateway data.
            gateway_id: Gateway ID for update, None for create.

        Returns:
            Saved gateway.

        Raises:
            Error: If gateway not found (update) or validation fails.
        """
        if gateway_id:
            self._logger.debug("save_started", gateway_id=str(gateway_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if gateway_id:
                gateway = await session.get(Gateway, gateway_id)
                if not gateway:
                    raise Error(ErrorCode.NOT_FOUND, "Gateway not found")

                if gateway.config.type != gateway_input.config.type:
                    raise Error(
                        ErrorCode.NOT_ALLOWED,
                        "Cannot change gateway config type",
                    )

                if gateway.agent_id != gateway_input.agent_id:
                    raise Error(
                        ErrorCode.NOT_ALLOWED,
                        "Cannot change gateway agent",
                    )

                gateway.name = gateway_input.name
                gateway.send_detailed_messages = gateway_input.send_detailed_messages
                gateway.error_code = gateway_input.error_code
                gateway.error_message = gateway_input.error_message
                gateway.config = gateway_input.config
            else:
                gateway = Gateway(
                    name=gateway_input.name,
                    send_detailed_messages=gateway_input.send_detailed_messages,
                    error_code=gateway_input.error_code,
                    error_message=gateway_input.error_message,
                    config=gateway_input.config,
                    agent_id=gateway_input.agent_id,
                )
                session.add(gateway)

            await session.commit()
            await session.refresh(gateway)

        if gateway_id:
            self._logger.debug("save_completed", gateway_id=str(gateway.id), mode="update")
        else:
            self._logger.debug("save_completed", gateway_id=str(gateway.id), mode="create")

        return gateway

    @handle_database_errors
    async def delete(self, gateway_id: UUID) -> None:
        """Delete gateway by ID.

        Args:
            gateway_id: Gateway ID.

        Raises:
            Error: If gateway not found.
        """
        self._logger.debug("delete_started", gateway_id=str(gateway_id))

        async with self._database.session() as session:
            gateway = await session.get(Gateway, gateway_id)
            if not gateway:
                raise Error(ErrorCode.NOT_FOUND, "Gateway not found")

            await session.delete(gateway)
            await session.commit()

        self._logger.debug("delete_completed", gateway_id=str(gateway_id))
