import grpc
from uuid import UUID
from google.protobuf.timestamp_pb2 import Timestamp
from ...common import Logger
from ...generated.proto.gateways import services_pb2_grpc, messages_pb2
from ...database import Database
from ...gateways import GatewayManager
from ...models import (
    Gateway,
    GatewayInput,
    GatewayConfig,
    GatewayConfigTelegram,
    GatewayConfigType,
    Error,
    ErrorCode,
)
from ..utils import handle_grpc_errors, python_error_code_to_proto


class GatewaysService(services_pb2_grpc.GatewaysServicer):
    """Gateways management service."""

    def __init__(self, database: Database, gateways: GatewayManager):
        """Initialize gateways service.

        Args:
            database: Database instance for data access.
            gateways: Gateway manager instance for triggering refresh on changes.
        """
        self._database = database
        self._gateways = gateways
        self._logger = Logger.get_logger("server.services.gateways")

    @handle_grpc_errors
    async def GetAll(
        self,
        request: messages_pb2.GetAllGatewaysRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetAllGatewaysRequest, messages_pb2.GetAllGatewaysResponse
        ],
    ) -> messages_pb2.GetAllGatewaysResponse:
        """Get all gateways."""
        agent_id = UUID(request.agent_id) if request.HasField("agent_id") else None

        if agent_id:
            self._logger.debug("get_all_called", agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_called")

        gateways = await self._database.gateways.get_all(agent_id)

        if agent_id:
            self._logger.debug("get_all_completed", count=len(gateways), agent_id=str(agent_id))
        else:
            self._logger.debug("get_all_completed", count=len(gateways))

        proto_gateways = [self._python_gateway_to_proto(gateway) for gateway in gateways]

        return messages_pb2.GetAllGatewaysResponse(gateways=proto_gateways)

    @handle_grpc_errors
    async def Get(
        self,
        request: messages_pb2.GetGatewayRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetGatewayRequest, messages_pb2.GetGatewayResponse
        ],
    ) -> messages_pb2.GetGatewayResponse:
        """Get gateway by ID."""
        gateway_id = UUID(request.id)
        self._logger.debug("get_called", gateway_id=str(gateway_id))

        gateway = await self._database.gateways.get(gateway_id)

        if not gateway:
            raise Error(ErrorCode.NOT_FOUND, "Gateway not found")

        self._logger.debug("get_completed", gateway_id=str(gateway_id))

        return messages_pb2.GetGatewayResponse(gateway=self._python_gateway_to_proto(gateway))

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveGatewayRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveGatewayRequest, messages_pb2.SaveGatewayResponse
        ],
    ) -> messages_pb2.SaveGatewayResponse:
        """Save gateway (create or update)."""
        gateway_id = UUID(request.id) if request.HasField("id") else None

        if gateway_id:
            self._logger.debug("save_called", gateway_id=str(gateway_id), mode="update")
        else:
            self._logger.debug("save_called", mode="create")

        gateway_config = self._proto_config_to_python(request.gateway.config)

        if gateway_id:
            existing_gateway = await self._database.gateways.get(gateway_id)
            if not existing_gateway:
                raise Error(ErrorCode.NOT_FOUND, "Gateway not found")

            error_code = existing_gateway.error_code
            error_message = existing_gateway.error_message
        else:
            error_code = None
            error_message = None

        gateway_input = GatewayInput(
            name=request.gateway.name,
            send_detailed_messages=request.gateway.send_detailed_messages,
            error_code=error_code,
            error_message=error_message,
            config=gateway_config,
            agent_id=UUID(request.gateway.agent_id),
        )

        gateway = await self._database.gateways.save(gateway_input, gateway_id)

        await self._gateways.refresh()

        if gateway_id:
            self._logger.debug("save_completed", gateway_id=str(gateway.id), mode="update")
        else:
            self._logger.debug("save_completed", gateway_id=str(gateway.id), mode="create")

        return messages_pb2.SaveGatewayResponse(gateway=self._python_gateway_to_proto(gateway))

    @handle_grpc_errors
    async def Delete(
        self,
        request: messages_pb2.DeleteGatewayRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.DeleteGatewayRequest, messages_pb2.DeleteGatewayResponse
        ],
    ) -> messages_pb2.DeleteGatewayResponse:
        """Delete gateway by ID."""
        gateway_id = UUID(request.id)
        self._logger.debug("delete_called", gateway_id=str(gateway_id))

        await self._database.gateways.delete(gateway_id)

        await self._gateways.refresh()

        self._logger.debug("delete_completed", gateway_id=str(gateway_id))

        return messages_pb2.DeleteGatewayResponse()

    def _python_gateway_to_proto(self, gateway: Gateway) -> messages_pb2.Gateway:
        """Convert Python Gateway to proto Gateway."""
        created_at_timestamp = Timestamp()
        created_at_timestamp.FromDatetime(gateway.created_at)

        updated_at_timestamp = Timestamp()
        updated_at_timestamp.FromDatetime(gateway.updated_at)

        proto_gateway = messages_pb2.Gateway(
            id=str(gateway.id),
            created_at=created_at_timestamp,
            updated_at=updated_at_timestamp,
            name=gateway.name,
            send_detailed_messages=gateway.send_detailed_messages,
            config=self._python_config_to_proto(gateway.config),
            agent_id=str(gateway.agent_id),
        )

        if gateway.error_code is not None:
            proto_gateway.error_code = python_error_code_to_proto(
                python_error_code=gateway.error_code
            )

        if gateway.error_message is not None:
            proto_gateway.error_message = gateway.error_message

        return proto_gateway

    def _python_config_to_proto(self, config: GatewayConfig) -> messages_pb2.GatewayConfig:
        """Convert Python GatewayConfig to proto GatewayConfig."""
        if config.type == GatewayConfigType.TELEGRAM:
            return messages_pb2.GatewayConfig(
                telegram=messages_pb2.GatewayConfigTelegram(
                    token=config.token,
                    allow_all=config.allow_all,
                    allowed_user_names=config.allowed_user_names,
                )
            )
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unknown gateway config type: {config.type}")

    def _proto_config_to_python(self, config: messages_pb2.GatewayConfig) -> GatewayConfig:
        """Convert proto GatewayConfig to Python GatewayConfig."""
        config_type = config.WhichOneof("config")

        match config_type:
            case "telegram":
                return GatewayConfigTelegram(
                    token=config.telegram.token,
                    allow_all=config.telegram.allow_all,
                    allowed_user_names=list(config.telegram.allowed_user_names),
                )
            case _:
                raise Error(ErrorCode.NOT_SUPPORTED, f"Unknown gateway config type: {config_type}")
