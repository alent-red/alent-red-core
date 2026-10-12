import grpc
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.providers import services_pb2_grpc, messages_pb2
from ...database import Database
from ...looper import Looper
from ...models import (
    Provider,
    ProviderInput,
    ProviderConfig,
    ProviderConfigAnthropic,
    ProviderConfigOpenAI,
    ProviderConfigLMStudio,
    ProviderConfigCustom,
    ProviderConfigType,
    ProviderApiFormat,
    ProviderApiFormatAnthropic,
    ProviderApiFormatAnthropicCacheTtl,
    ProviderApiFormatOpenAiChatCompletions,
    ProviderApiFormatOpenAiResponses,
    ProviderApiFormatType,
    Error,
    ErrorCode,
)
from ..utils import handle_grpc_errors


class ProvidersService(services_pb2_grpc.ProvidersServicer):
    """Providers management service."""

    def __init__(self, database: Database, looper: Looper):
        """Initialize providers service.

        Args:
            database: Database instance for data access.
            looper: Looper instance for triggering refresh on changes.
        """
        self._database = database
        self._looper = looper
        self._logger = Logger.get_logger("server.services.providers")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllProvidersRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllProvidersRequest, messages_pb2.GetAllProvidersResponse
        ],
    ) -> messages_pb2.GetAllProvidersResponse:
        """Get all providers."""
        self._logger.debug("get_all_called")

        providers = await self._database.providers.get_all()

        self._logger.debug("get_all_completed", count=len(providers))

        proto_providers = [self._python_provider_to_proto(provider) for provider in providers]

        return messages_pb2.GetAllProvidersResponse(providers=proto_providers)

    @handle_grpc_errors
    async def Get(
        self,
        request: messages_pb2.GetProviderRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetProviderRequest, messages_pb2.GetProviderResponse
        ],
    ) -> messages_pb2.GetProviderResponse:
        """Get provider by ID."""
        provider_id = UUID(request.id)
        self._logger.debug("get_called", provider_id=str(provider_id))

        provider = await self._database.providers.get(provider_id)

        if not provider:
            raise Error(ErrorCode.NOT_FOUND, "Provider not found")

        self._logger.debug("get_completed", provider_id=str(provider_id))

        return messages_pb2.GetProviderResponse(provider=self._python_provider_to_proto(provider))

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveProviderRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveProviderRequest, messages_pb2.SaveProviderResponse
        ],
    ) -> messages_pb2.SaveProviderResponse:
        """Save provider (create or update)."""
        provider_id = UUID(request.id) if request.HasField("id") else None

        if provider_id:
            self._logger.debug("save_called", provider_id=str(provider_id), mode="update")
        else:
            self._logger.debug("save_called", mode="create")

        provider_input = ProviderInput(
            name=request.provider.name,
            config=self._proto_config_to_python(request.provider.config),
        )

        provider = await self._database.providers.save(provider_input, provider_id)

        await self._looper.refresh()

        if provider_id:
            self._logger.debug("save_completed", provider_id=str(provider.id), mode="update")
        else:
            self._logger.debug("save_completed", provider_id=str(provider.id), mode="create")

        return messages_pb2.SaveProviderResponse(provider=self._python_provider_to_proto(provider))

    @handle_grpc_errors
    async def Delete(
        self,
        request: messages_pb2.DeleteProviderRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.DeleteProviderRequest, messages_pb2.DeleteProviderResponse
        ],
    ) -> messages_pb2.DeleteProviderResponse:
        """Delete provider by ID."""
        provider_id = UUID(request.id)
        self._logger.debug("delete_called", provider_id=str(provider_id))

        await self._database.providers.delete(provider_id)

        await self._looper.refresh()

        self._logger.debug("delete_completed", provider_id=str(provider_id))

        return messages_pb2.DeleteProviderResponse()

    def _proto_config_to_python(self, proto_config: messages_pb2.ProviderConfig) -> ProviderConfig:
        """Convert proto ProviderConfig to Python ProviderConfig."""
        which = proto_config.WhichOneof("config")

        if which == "anthropic":
            return ProviderConfigAnthropic(api_key=proto_config.anthropic.api_key)
        elif which == "openai":
            return ProviderConfigOpenAI(api_key=proto_config.openai.api_key)
        elif which == "lm_studio":
            return ProviderConfigLMStudio(base_url=proto_config.lm_studio.base_url)
        elif which == "custom":
            custom = proto_config.custom
            return ProviderConfigCustom(
                base_url=custom.base_url,
                api_key=custom.api_key if custom.HasField("api_key") else None,
                api_format=self._proto_api_format_to_python(custom.api_format),
            )
        else:
            raise ValueError(f"Unknown provider config type: {which}")

    def _python_config_to_proto(self, python_config: ProviderConfig) -> messages_pb2.ProviderConfig:
        """Convert Python ProviderConfig to proto ProviderConfig."""
        if python_config.type == ProviderConfigType.ANTHROPIC:
            return messages_pb2.ProviderConfig(
                anthropic=messages_pb2.ProviderConfigAnthropic(api_key=python_config.api_key)
            )
        elif python_config.type == ProviderConfigType.OPENAI:
            return messages_pb2.ProviderConfig(
                openai=messages_pb2.ProviderConfigOpenAI(api_key=python_config.api_key)
            )
        elif python_config.type == ProviderConfigType.LM_STUDIO:
            return messages_pb2.ProviderConfig(
                lm_studio=messages_pb2.ProviderConfigLMStudio(base_url=str(python_config.base_url))
            )
        elif python_config.type == ProviderConfigType.CUSTOM:
            custom_proto = messages_pb2.ProviderConfigCustom(
                base_url=str(python_config.base_url),
                api_format=self._python_api_format_to_proto(python_config.api_format),
            )
            if python_config.api_key is not None:
                custom_proto.api_key = python_config.api_key
            return messages_pb2.ProviderConfig(custom=custom_proto)
        else:
            raise ValueError(f"Unknown provider config type: {python_config.type}")

    def _proto_api_format_to_python(
        self, proto_format: messages_pb2.ProviderApiFormat
    ) -> ProviderApiFormat:
        """Convert proto ProviderApiFormat to Python union."""
        which = proto_format.WhichOneof("format")

        if which == "anthropic":
            return ProviderApiFormatAnthropic(
                reasoning_minimal_budget_tokens=proto_format.anthropic.reasoning_minimal_budget_tokens,
                reasoning_low_budget_tokens=proto_format.anthropic.reasoning_low_budget_tokens,
                reasoning_medium_budget_tokens=proto_format.anthropic.reasoning_medium_budget_tokens,
                reasoning_high_budget_tokens=proto_format.anthropic.reasoning_high_budget_tokens,
                reasoning_xhigh_budget_tokens=proto_format.anthropic.reasoning_xhigh_budget_tokens,
                cache_medium_ttl=self._proto_cache_ttl_to_python(
                    proto_format.anthropic.cache_medium_ttl
                ),
                cache_high_ttl=self._proto_cache_ttl_to_python(
                    proto_format.anthropic.cache_high_ttl
                ),
                input_tokens_include_cache=False,
            )
        elif which == "openai_chat_completions":
            return ProviderApiFormatOpenAiChatCompletions()
        elif which == "openai_responses":
            return ProviderApiFormatOpenAiResponses()
        else:
            raise ValueError(f"Unknown provider API format: {which}")

    def _python_api_format_to_proto(
        self, python_format: ProviderApiFormat
    ) -> messages_pb2.ProviderApiFormat:
        """Convert Python ProviderApiFormat to proto message."""
        if python_format.type == ProviderApiFormatType.ANTHROPIC:
            return messages_pb2.ProviderApiFormat(
                anthropic=messages_pb2.ProviderApiFormatAnthropic(
                    reasoning_minimal_budget_tokens=python_format.reasoning_minimal_budget_tokens,
                    reasoning_low_budget_tokens=python_format.reasoning_low_budget_tokens,
                    reasoning_medium_budget_tokens=python_format.reasoning_medium_budget_tokens,
                    reasoning_high_budget_tokens=python_format.reasoning_high_budget_tokens,
                    reasoning_xhigh_budget_tokens=python_format.reasoning_xhigh_budget_tokens,
                    cache_medium_ttl=self._python_cache_ttl_to_proto(
                        python_format.cache_medium_ttl
                    ),
                    cache_high_ttl=self._python_cache_ttl_to_proto(python_format.cache_high_ttl),
                )
            )
        elif python_format.type == ProviderApiFormatType.OPENAI_CHAT_COMPLETIONS:
            return messages_pb2.ProviderApiFormat(
                openai_chat_completions=messages_pb2.ProviderApiFormatOpenAiChatCompletions()
            )
        elif python_format.type == ProviderApiFormatType.OPENAI_RESPONSES:
            return messages_pb2.ProviderApiFormat(
                openai_responses=messages_pb2.ProviderApiFormatOpenAiResponses()
            )
        else:
            raise ValueError(f"Unknown provider API format type: {python_format.type}")

    def _proto_cache_ttl_to_python(
        self, proto_cache_ttl: messages_pb2.ProviderApiFormatAnthropicCacheTtl
    ) -> ProviderApiFormatAnthropicCacheTtl:
        """Convert proto ProviderApiFormatAnthropicCacheTtl to Python enum."""
        if proto_cache_ttl == messages_pb2.PROVIDER_API_FORMAT_ANTHROPIC_CACHE_TTL_DEFAULT:
            return ProviderApiFormatAnthropicCacheTtl.DEFAULT
        elif proto_cache_ttl == messages_pb2.PROVIDER_API_FORMAT_ANTHROPIC_CACHE_TTL_MIN_5:
            return ProviderApiFormatAnthropicCacheTtl.MIN_5
        elif proto_cache_ttl == messages_pb2.PROVIDER_API_FORMAT_ANTHROPIC_CACHE_TTL_HOUR_1:
            return ProviderApiFormatAnthropicCacheTtl.HOUR_1
        else:
            raise ValueError(f"Unknown Anthropic cache TTL: {proto_cache_ttl}")

    def _python_cache_ttl_to_proto(
        self, python_cache_ttl: ProviderApiFormatAnthropicCacheTtl
    ) -> messages_pb2.ProviderApiFormatAnthropicCacheTtl:
        """Convert Python ProviderApiFormatAnthropicCacheTtl to proto enum."""
        if python_cache_ttl == ProviderApiFormatAnthropicCacheTtl.DEFAULT:
            return messages_pb2.PROVIDER_API_FORMAT_ANTHROPIC_CACHE_TTL_DEFAULT
        elif python_cache_ttl == ProviderApiFormatAnthropicCacheTtl.MIN_5:
            return messages_pb2.PROVIDER_API_FORMAT_ANTHROPIC_CACHE_TTL_MIN_5
        elif python_cache_ttl == ProviderApiFormatAnthropicCacheTtl.HOUR_1:
            return messages_pb2.PROVIDER_API_FORMAT_ANTHROPIC_CACHE_TTL_HOUR_1
        else:
            raise ValueError(f"Unknown Anthropic cache TTL: {python_cache_ttl}")

    def _python_provider_to_proto(self, python_provider: Provider) -> messages_pb2.Provider:
        """Convert Python Provider to proto Provider."""
        created_at = Timestamp()
        created_at.FromDatetime(python_provider.created_at)

        updated_at = Timestamp()
        updated_at.FromDatetime(python_provider.updated_at)

        return messages_pb2.Provider(
            id=str(python_provider.id),
            created_at=created_at,
            updated_at=updated_at,
            name=python_provider.name,
            config=self._python_config_to_proto(python_provider.config),
        )
