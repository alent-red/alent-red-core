from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import select, column
from ...common import Logger
from ...models import Agent, AgentInput, AgentBrick, Error, ErrorCode
from ..utils import handle_database_errors

if TYPE_CHECKING:
    from ..database import Database


class AgentStore:
    """Manages agent storage operations."""

    def __init__(self, database: Database):
        """Initialize agent store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.agent_store")

    @handle_database_errors
    async def get_all(
        self, llm_model_id: UUID | None = None, brick_id: UUID | None = None
    ) -> list[Agent]:
        """Get all agents.

        Args:
            llm_model_id: Optional LLM model ID to filter by.
            brick_id: Optional brick ID to filter by.

        Returns:
            List of all agents, optionally filtered by LLM model or brick.
        """
        filters = []
        if llm_model_id:
            filters.append(f"llm_model_id={str(llm_model_id)}")
        if brick_id:
            filters.append(f"brick_id={str(brick_id)}")

        if filters:
            self._logger.debug(
                "get_all_started", **{f.split("=")[0]: f.split("=")[1] for f in filters}
            )
        else:
            self._logger.debug("get_all_started")

        async with self._database.session() as session:
            query = select(Agent)

            if llm_model_id:
                query = query.where(column("llm_model_id") == llm_model_id)

            if brick_id:
                query = query.join(AgentBrick).where(column("brick_id") == brick_id)

            result = await session.execute(query)
            agents = list(result.scalars().all())

        if filters:
            self._logger.debug(
                "get_all_completed",
                count=len(agents),
                **{f.split("=")[0]: f.split("=")[1] for f in filters},
            )
        else:
            self._logger.debug("get_all_completed", count=len(agents))

        return agents

    @handle_database_errors
    async def get(self, agent_id: UUID) -> Agent | None:
        """Get agent by ID.

        Args:
            agent_id: Agent ID.

        Returns:
            Agent if found, None otherwise.
        """
        self._logger.debug("get_started", agent_id=str(agent_id))

        async with self._database.session() as session:
            agent = await session.get(Agent, agent_id)

        self._logger.debug("get_completed", agent_id=str(agent_id), found=agent is not None)

        return agent

    @handle_database_errors
    async def save(self, agent_input: AgentInput, agent_id: UUID | None) -> Agent:
        """Save agent (create new or update existing).

        Args:
            agent_input: Agent data to save.
            agent_id: Agent ID to update (None for new agent).

        Returns:
            Saved agent.

        Raises:
            Error: If agent not found (update mode), name duplicated, or llm_model_id foreign key violation.
        """
        if agent_id:
            self._logger.debug("save_started", agent_id=str(agent_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if agent_id:
                agent = await session.get(Agent, agent_id)

                if not agent:
                    raise Error(ErrorCode.NOT_FOUND, "Agent not found")

                agent.name = agent_input.name
                agent.picture_file_key = agent_input.picture_file_key
                agent.prompt = agent_input.prompt
                agent.attached_file_paths = agent_input.attached_file_paths
                agent.reasoning = agent_input.reasoning
                agent.verbosity = agent_input.verbosity
                agent.llm_model_id = agent_input.llm_model_id
            else:
                agent = Agent(
                    name=agent_input.name,
                    picture_file_key=agent_input.picture_file_key,
                    prompt=agent_input.prompt,
                    attached_file_paths=agent_input.attached_file_paths,
                    reasoning=agent_input.reasoning,
                    verbosity=agent_input.verbosity,
                    llm_model_id=agent_input.llm_model_id,
                )
                session.add(agent)

            await session.flush()

            result = await session.execute(select(AgentBrick).where(column("agent_id") == agent.id))
            existing_agent_bricks = list(result.scalars().all())
            existing_brick_ids = {agent_brick.brick_id for agent_brick in existing_agent_bricks}
            desired_brick_ids = set(agent_input.brick_ids)

            for agent_brick in existing_agent_bricks:
                if agent_brick.brick_id not in desired_brick_ids:
                    await session.delete(agent_brick)

            for brick_id in desired_brick_ids - existing_brick_ids:
                session.add(AgentBrick(agent_id=agent.id, brick_id=brick_id))

            await session.commit()
            await session.refresh(agent)

        if agent_id:
            self._logger.debug("save_completed", agent_id=str(agent.id), mode="update")
        else:
            self._logger.debug("save_completed", agent_id=str(agent.id), mode="create")

        return agent

    @handle_database_errors
    async def delete(self, agent_id: UUID) -> None:
        """Delete agent by ID.

        Args:
            agent_id: Agent ID to delete.

        Raises:
            Error: If agent not found.
        """
        self._logger.debug("delete_started", agent_id=str(agent_id))

        async with self._database.session() as session:
            agent = await session.get(Agent, agent_id)
            if not agent:
                raise Error(ErrorCode.NOT_FOUND, "Agent not found")

            await session.delete(agent)
            await session.commit()

        self._logger.debug("delete_completed", agent_id=str(agent_id))
