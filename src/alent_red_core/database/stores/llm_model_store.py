from uuid import UUID
from sqlalchemy import select, column
from typing import TYPE_CHECKING

from ...common import Logger
from ...models import LlmModel, LlmModelInput, Error, ErrorCode
from ..utils import handle_database_errors

if TYPE_CHECKING:
    from ..database import Database


class LlmModelStore:
    """Manages LLM model storage operations."""

    def __init__(self, database: "Database"):
        """Initialize LLM model store.

        Args:
            database: Database instance for session management.
        """
        self._database = database
        self._logger = Logger.get_logger("database.stores.llm_model_store")

    @handle_database_errors
    async def get_all(self, provider_id: UUID | None = None) -> list[LlmModel]:
        """Get all LLM models.

        Args:
            provider_id: Optional provider ID to filter by.

        Returns:
            List of all LLM models, optionally filtered by provider.
        """
        if provider_id:
            self._logger.debug("get_all_started", provider_id=str(provider_id))
        else:
            self._logger.debug("get_all_started")

        async with self._database.session() as session:
            if provider_id:
                result = await session.execute(
                    select(LlmModel).where(column("provider_id") == provider_id)
                )
            else:
                result = await session.execute(select(LlmModel))
            llm_models = list(result.scalars().all())

        if provider_id:
            self._logger.debug(
                "get_all_completed", count=len(llm_models), provider_id=str(provider_id)
            )
        else:
            self._logger.debug("get_all_completed", count=len(llm_models))
        return llm_models

    @handle_database_errors
    async def get(self, llm_model_id: UUID) -> LlmModel | None:
        """Get LLM model by ID.

        Args:
            llm_model_id: LLM model ID.

        Returns:
            LLM model if found, None otherwise.
        """
        self._logger.debug("get_started", llm_model_id=str(llm_model_id))

        async with self._database.session() as session:
            llm_model = await session.get(LlmModel, llm_model_id)

        found = llm_model is not None
        self._logger.debug("get_completed", llm_model_id=str(llm_model_id), found=found)
        return llm_model

    @handle_database_errors
    async def save(
        self, llm_model_input: LlmModelInput, llm_model_id: UUID | None = None
    ) -> LlmModel:
        """Save LLM model (create or update).

        Args:
            llm_model_input: LLM model data.
            llm_model_id: LLM model ID for update, None for create.

        Returns:
            Saved LLM model.

        Raises:
            Error: If LLM model not found (update) or validation fails.
        """
        if llm_model_id:
            self._logger.debug("save_started", llm_model_id=str(llm_model_id), mode="update")
        else:
            self._logger.debug("save_started", mode="create")

        async with self._database.session() as session:
            if llm_model_id:
                llm_model = await session.get(LlmModel, llm_model_id)
                if not llm_model:
                    raise Error(ErrorCode.NOT_FOUND, "LLM model not found")

                llm_model.name = llm_model_input.name
                llm_model.model_id = llm_model_input.model_id
                llm_model.context_window_tokens_count = llm_model_input.context_window_tokens_count
                llm_model.max_output_tokens_count = llm_model_input.max_output_tokens_count
                llm_model.top_p = llm_model_input.top_p
                llm_model.image_detail = llm_model_input.image_detail
                llm_model.cache = llm_model_input.cache
                llm_model.provider_id = llm_model_input.provider_id
            else:
                llm_model = LlmModel(
                    name=llm_model_input.name,
                    model_id=llm_model_input.model_id,
                    context_window_tokens_count=llm_model_input.context_window_tokens_count,
                    max_output_tokens_count=llm_model_input.max_output_tokens_count,
                    top_p=llm_model_input.top_p,
                    image_detail=llm_model_input.image_detail,
                    cache=llm_model_input.cache,
                    provider_id=llm_model_input.provider_id,
                )
                session.add(llm_model)

            await session.commit()
            await session.refresh(llm_model)

        if llm_model_id:
            self._logger.debug("save_completed", llm_model_id=str(llm_model.id), mode="update")
        else:
            self._logger.debug("save_completed", llm_model_id=str(llm_model.id), mode="create")

        return llm_model

    @handle_database_errors
    async def delete(self, llm_model_id: UUID) -> None:
        """Delete LLM model by ID.

        Args:
            llm_model_id: LLM model ID.

        Raises:
            Error: If LLM model not found.
        """
        self._logger.debug("delete_started", llm_model_id=str(llm_model_id))

        async with self._database.session() as session:
            llm_model = await session.get(LlmModel, llm_model_id)
            if not llm_model:
                raise Error(ErrorCode.NOT_FOUND, "LLM model not found")

            await session.delete(llm_model)
            await session.commit()

        self._logger.debug("delete_completed", llm_model_id=str(llm_model_id))
