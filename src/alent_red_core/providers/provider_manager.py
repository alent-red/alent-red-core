from uuid import UUID
from typing import AsyncIterator

from ..common import Logger
from ..models import (
    AgentReasoning,
    AgentVerbosity,
    Blob,
    Error,
    ErrorCode,
    LlmModel,
    LlmResponse,
    LlmStreamItem,
    MessageContent,
    MessageContentType,
    Tool,
)
from ..database import Database
from ..blob import BlobStorage
from .base_provider import BaseProvider
from .provider_builder import ProviderBuilder


class ProviderManager:
    """Manages lifecycle and orchestration of all provider instances."""

    def __init__(self, database: Database, blob: BlobStorage):
        """Initialize provider manager.

        Args:
            database: Database instance.
            blob: Blob storage instance.
        """
        self._database = database
        self._blob = blob
        self._providers: dict[UUID, BaseProvider] = {}
        self._logger = Logger.get_logger("providers.provider_manager")

    async def setup(self) -> None:
        """Setup the provider manager and initialize all providers."""
        self._logger.debug("setup_started")

        providers = await self._database.providers.get_all()
        for provider in providers:
            provider_instance = await ProviderBuilder.build(provider, self._database)
            self._providers[provider.id] = provider_instance

        self._logger.debug("setup_completed", count=len(self._providers))

    async def refresh(self) -> None:
        """Refresh all providers from database."""
        self._logger.debug("refresh_started")

        providers = await self._database.providers.get_all()
        db_provider_ids = {provider.id for provider in providers}
        current_provider_ids = set(self._providers.keys())

        for provider in providers:
            if provider.id in self._providers:
                await self._providers[provider.id].refresh(provider.config)
            else:
                provider_instance = await ProviderBuilder.build(provider, self._database)
                self._providers[provider.id] = provider_instance

        removed_provider_ids = current_provider_ids - db_provider_ids
        for provider_id in removed_provider_ids:
            await self._providers[provider_id].clean()
            del self._providers[provider_id]

        self._logger.debug(
            "refresh_completed",
            count=len(self._providers),
            added=len(db_provider_ids - current_provider_ids),
            removed=len(removed_provider_ids),
        )

    async def clean(self) -> None:
        """Clean the provider manager and cleanup all providers."""
        self._logger.debug("clean_started", count=len(self._providers))

        for provider in self._providers.values():
            await provider.clean()
        self._providers.clear()

        self._logger.debug("clean_completed")

    async def llm(
        self,
        system_prompt: str | None,
        messages: list[MessageContent],
        tools: list[Tool] | None,
        llm_model: LlmModel,
        reasoning: AgentReasoning,
        verbosity: AgentVerbosity,
    ) -> LlmResponse:
        """Generate LLM response without streaming.

        Args:
            system_prompt: System prompt or None.
            messages: List of message content.
            tools: List of available tools.
            llm_model: LLM model configuration.
            reasoning: Agent reasoning mode.
            verbosity: Agent verbosity level.

        Returns:
            The contents produced and the usage of the call.

        Raises:
            Error: If provider not found.
        """
        provider_id = llm_model.provider_id
        self._logger.debug(
            "llm_started",
            provider_id=str(provider_id),
            model_id=llm_model.model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            has_system_prompt=system_prompt is not None,
        )

        if provider_id not in self._providers:
            raise Error(ErrorCode.NOT_FOUND, f"Provider {provider_id} not found")

        image_blobs = await self._build_image_blobs(messages)

        result = await self._providers[provider_id].llm(
            system_prompt=system_prompt,
            messages=messages,
            image_blobs=image_blobs,
            tools=tools,
            model_id=llm_model.model_id,
            max_output_tokens_count=llm_model.max_output_tokens_count,
            top_p=llm_model.top_p,
            image_detail=llm_model.image_detail,
            cache=llm_model.cache,
            reasoning=reasoning,
            verbosity=verbosity,
        )

        self._logger.debug("llm_completed", response_content_count=len(result.contents))

        return result

    async def llm_stream(
        self,
        system_prompt: str | None,
        messages: list[MessageContent],
        tools: list[Tool] | None,
        llm_model: LlmModel,
        reasoning: AgentReasoning,
        verbosity: AgentVerbosity,
    ) -> AsyncIterator[LlmStreamItem]:
        """Generate LLM response with streaming.

        Args:
            system_prompt: System prompt or None.
            messages: List of message content.
            tools: List of available tools.
            llm_model: LLM model configuration.
            reasoning: Agent reasoning mode.
            verbosity: Agent verbosity level.

        Yields:
            Message content chunks from LLM, then the usage of the call.

        Raises:
            Error: If provider not found.
        """
        provider_id = llm_model.provider_id
        self._logger.debug(
            "llm_stream_started",
            provider_id=str(provider_id),
            model_id=llm_model.model_id,
            message_count=len(messages),
            tool_count=len(tools) if tools else 0,
            has_system_prompt=system_prompt is not None,
        )

        if provider_id not in self._providers:
            raise Error(ErrorCode.NOT_FOUND, f"Provider {provider_id} not found")

        image_blobs = await self._build_image_blobs(messages)

        chunk_count = 0
        async for content in self._providers[provider_id].llm_stream(
            system_prompt=system_prompt,
            messages=messages,
            image_blobs=image_blobs,
            tools=tools,
            model_id=llm_model.model_id,
            max_output_tokens_count=llm_model.max_output_tokens_count,
            top_p=llm_model.top_p,
            image_detail=llm_model.image_detail,
            cache=llm_model.cache,
            reasoning=reasoning,
            verbosity=verbosity,
        ):
            chunk_count += 1
            yield content

        self._logger.debug("llm_stream_completed", chunk_count=chunk_count)

    async def _build_image_blobs(self, messages: list[MessageContent]) -> dict[str, Blob]:
        """Build image blobs dictionary from messages.

        Args:
            messages: List of message content.

        Returns:
            Dictionary mapping blob keys to Blob objects.

        Raises:
            Error: If blob cannot be read.
        """
        image_blobs: dict[str, Blob] = {}

        for message in messages:
            if message.type == MessageContentType.TOOL and message.response:
                for image_key in message.response.image_file_keys:
                    blob = await self._blob.read(image_key)
                    if blob is not None:
                        image_blobs[image_key] = blob

        return image_blobs
