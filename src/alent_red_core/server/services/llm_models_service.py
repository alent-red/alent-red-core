import grpc
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.llm_models import services_pb2_grpc, messages_pb2
from ...database import Database
from ...looper import Looper
from ...models import LlmModel, LlmModelInput, LlmModelImageDetail, LlmModelCache, Error, ErrorCode
from ..utils import handle_grpc_errors


class LlmModelsService(services_pb2_grpc.LlmModelsServicer):
    """LLM models management service."""

    def __init__(self, database: Database, looper: Looper):
        """Initialize LLM models service.

        Args:
            database: Database instance for data access.
            looper: Looper instance for triggering refresh on changes.
        """
        self._database = database
        self._looper = looper
        self._logger = Logger.get_logger("server.services.llm_models")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllLlmModelsRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllLlmModelsRequest, messages_pb2.GetAllLlmModelsResponse
        ],
    ) -> messages_pb2.GetAllLlmModelsResponse:
        """Get all LLM models."""

        provider_id = UUID(request.provider_id) if request.HasField("provider_id") else None

        if provider_id:
            self._logger.debug("get_all_called", provider_id=str(provider_id))
        else:
            self._logger.debug("get_all_called")

        llm_models = await self._database.llm_models.get_all(provider_id)

        if provider_id:
            self._logger.debug(
                "get_all_completed", count=len(llm_models), provider_id=str(provider_id)
            )
        else:
            self._logger.debug("get_all_completed", count=len(llm_models))

        proto_llm_models = [self._python_llm_model_to_proto(llm_model) for llm_model in llm_models]

        return messages_pb2.GetAllLlmModelsResponse(llm_models=proto_llm_models)

    @handle_grpc_errors
    async def Get(
        self,
        request: messages_pb2.GetLlmModelRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetLlmModelRequest, messages_pb2.GetLlmModelResponse
        ],
    ) -> messages_pb2.GetLlmModelResponse:
        """Get LLM model by ID."""
        llm_model_id = UUID(request.id)
        self._logger.debug("get_called", llm_model_id=str(llm_model_id))

        llm_model = await self._database.llm_models.get(llm_model_id)

        if not llm_model:
            raise Error(ErrorCode.NOT_FOUND, "LLM model not found")

        self._logger.debug("get_completed", llm_model_id=str(llm_model_id))

        return messages_pb2.GetLlmModelResponse(
            llm_model=self._python_llm_model_to_proto(llm_model)
        )

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveLlmModelRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveLlmModelRequest, messages_pb2.SaveLlmModelResponse
        ],
    ) -> messages_pb2.SaveLlmModelResponse:
        """Save LLM model (create or update)."""
        llm_model_id = UUID(request.id) if request.HasField("id") else None

        if llm_model_id:
            self._logger.debug("save_called", llm_model_id=str(llm_model_id), mode="update")
        else:
            self._logger.debug("save_called", mode="create")

        llm_model_input = LlmModelInput(
            name=request.llm_model.name,
            model_id=request.llm_model.model_id,
            context_window_tokens_count=request.llm_model.context_window_tokens_count,
            max_output_tokens_count=request.llm_model.max_output_tokens_count,
            top_p=request.llm_model.top_p,
            image_detail=self._proto_image_detail_to_python(request.llm_model.image_detail),
            cache=self._proto_cache_to_python(request.llm_model.cache),
            provider_id=UUID(request.llm_model.provider_id),
        )

        self._logger.debug("save_validated", llm_model_input=str(llm_model_input))

        llm_model = await self._database.llm_models.save(llm_model_input, llm_model_id)

        await self._looper.refresh()

        if llm_model_id:
            self._logger.debug("save_completed", llm_model_id=str(llm_model.id), mode="update")
        else:
            self._logger.debug("save_completed", llm_model_id=str(llm_model.id), mode="create")

        return messages_pb2.SaveLlmModelResponse(
            llm_model=self._python_llm_model_to_proto(llm_model)
        )

    @handle_grpc_errors
    async def Delete(
        self,
        request: messages_pb2.DeleteLlmModelRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.DeleteLlmModelRequest, messages_pb2.DeleteLlmModelResponse
        ],
    ) -> messages_pb2.DeleteLlmModelResponse:
        """Delete LLM model by ID."""
        llm_model_id = UUID(request.id)
        self._logger.debug("delete_called", llm_model_id=str(llm_model_id))

        await self._database.llm_models.delete(llm_model_id)

        await self._looper.refresh()

        self._logger.debug("delete_completed", llm_model_id=str(llm_model_id))

        return messages_pb2.DeleteLlmModelResponse()

    def _python_llm_model_to_proto(self, python_llm_model: LlmModel) -> messages_pb2.LlmModel:
        """Convert Python LlmModel to proto LlmModel."""
        created_at = Timestamp()
        created_at.FromDatetime(python_llm_model.created_at)

        updated_at = Timestamp()
        updated_at.FromDatetime(python_llm_model.updated_at)

        return messages_pb2.LlmModel(
            id=str(python_llm_model.id),
            created_at=created_at,
            updated_at=updated_at,
            name=python_llm_model.name,
            model_id=python_llm_model.model_id,
            context_window_tokens_count=python_llm_model.context_window_tokens_count,
            max_output_tokens_count=python_llm_model.max_output_tokens_count,
            top_p=python_llm_model.top_p,
            image_detail=self._python_image_detail_to_proto(python_llm_model.image_detail),
            cache=self._python_cache_to_proto(python_llm_model.cache),
            provider_id=str(python_llm_model.provider_id),
        )

    def _proto_image_detail_to_python(
        self, proto_image_detail: messages_pb2.LlmModelImageDetail
    ) -> LlmModelImageDetail:
        """Convert proto LlmModelImageDetail to Python enum."""
        if proto_image_detail == messages_pb2.LLM_MODEL_IMAGE_DETAIL_DEFAULT:
            return LlmModelImageDetail.DEFAULT
        elif proto_image_detail == messages_pb2.LLM_MODEL_IMAGE_DETAIL_LOW:
            return LlmModelImageDetail.LOW
        elif proto_image_detail == messages_pb2.LLM_MODEL_IMAGE_DETAIL_HIGH:
            return LlmModelImageDetail.HIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid image detail value")

    def _python_image_detail_to_proto(
        self, python_image_detail: LlmModelImageDetail
    ) -> messages_pb2.LlmModelImageDetail:
        """Convert Python LlmModelImageDetail to proto enum."""
        if python_image_detail == LlmModelImageDetail.DEFAULT:
            return messages_pb2.LLM_MODEL_IMAGE_DETAIL_DEFAULT
        elif python_image_detail == LlmModelImageDetail.LOW:
            return messages_pb2.LLM_MODEL_IMAGE_DETAIL_LOW
        elif python_image_detail == LlmModelImageDetail.HIGH:
            return messages_pb2.LLM_MODEL_IMAGE_DETAIL_HIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid image detail value")

    def _proto_cache_to_python(self, proto_cache: messages_pb2.LlmModelCache) -> LlmModelCache:
        """Convert proto LlmModelCache to Python enum."""
        if proto_cache == messages_pb2.LLM_MODEL_CACHE_DEFAULT:
            return LlmModelCache.DEFAULT
        elif proto_cache == messages_pb2.LLM_MODEL_CACHE_MEDIUM:
            return LlmModelCache.MEDIUM
        elif proto_cache == messages_pb2.LLM_MODEL_CACHE_HIGH:
            return LlmModelCache.HIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid cache value")

    def _python_cache_to_proto(self, python_cache: LlmModelCache) -> messages_pb2.LlmModelCache:
        """Convert Python LlmModelCache to proto enum."""
        if python_cache == LlmModelCache.DEFAULT:
            return messages_pb2.LLM_MODEL_CACHE_DEFAULT
        elif python_cache == LlmModelCache.MEDIUM:
            return messages_pb2.LLM_MODEL_CACHE_MEDIUM
        elif python_cache == LlmModelCache.HIGH:
            return messages_pb2.LLM_MODEL_CACHE_HIGH
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, "Invalid cache value")
