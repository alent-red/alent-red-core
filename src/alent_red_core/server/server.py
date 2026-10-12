from typing import Callable, Optional
import grpc.aio
from grpc_reflection.v1alpha import reflection
from google.protobuf.descriptor import ServiceDescriptor
from .services import (
    InfoService,
    PreferencesService,
    ProvidersService,
    LlmModelsService,
    AgentsService,
    BricksService,
    GatewaysService,
    ConversationsService,
    MessagesService,
    BlobService,
)
from ..generated.proto.info import (
    services_pb2 as info_services_pb2,
    services_pb2_grpc as info_services_pb2_grpc,
)
from ..generated.proto.preferences import (
    services_pb2 as preferences_services_pb2,
    services_pb2_grpc as preferences_services_pb2_grpc,
)
from ..generated.proto.providers import (
    services_pb2 as providers_services_pb2,
    services_pb2_grpc as providers_services_pb2_grpc,
)
from ..generated.proto.llm_models import (
    services_pb2 as llm_models_services_pb2,
    services_pb2_grpc as llm_models_services_pb2_grpc,
)
from ..generated.proto.agents import (
    services_pb2 as agents_services_pb2,
    services_pb2_grpc as agents_services_pb2_grpc,
)
from ..generated.proto.bricks import (
    services_pb2 as bricks_services_pb2,
    services_pb2_grpc as bricks_services_pb2_grpc,
)
from ..generated.proto.gateways import (
    services_pb2 as gateways_services_pb2,
    services_pb2_grpc as gateways_services_pb2_grpc,
)
from ..generated.proto.conversations import (
    services_pb2 as conversations_services_pb2,
    services_pb2_grpc as conversations_services_pb2_grpc,
)
from ..generated.proto.messages import (
    services_pb2 as messages_services_pb2,
    services_pb2_grpc as messages_services_pb2_grpc,
)
from ..generated.proto.blob import (
    services_pb2 as blob_services_pb2,
    services_pb2_grpc as blob_services_pb2_grpc,
)
from ..database import Database
from ..blob import BlobStorage
from ..looper import Looper
from ..gateways import GatewayManager
from ..common import Logger


class Server:
    """Manages gRPC server lifecycle and service registration."""

    def __init__(
        self,
        version: str,
        database: Database,
        blob: BlobStorage,
        looper: Looper,
        gateways: GatewayManager,
    ):
        """Initialize the server with automatic service registration.

        Args:
            version: Application version string.
            database: Database instance for data access.
            blob: Blob storage instance for encrypted file access.
            looper: Looper instance for triggering refresh and processing.
            gateways: Gateway manager instance for triggering refresh on changes.
        """
        self._server: Optional[grpc.aio.Server] = None
        self._servicers: list[
            tuple[Callable[[object, grpc.aio.Server], None], object, ServiceDescriptor]
        ] = []
        self._logger = Logger.get_logger("server.server")

        info_service = InfoService(version)
        self._servicers.append(
            (
                info_services_pb2_grpc.add_InfoServicer_to_server,
                info_service,
                info_services_pb2.DESCRIPTOR.services_by_name["Info"],
            )
        )

        preferences_service = PreferencesService(database, looper, gateways)
        self._servicers.append(
            (
                preferences_services_pb2_grpc.add_PreferencesServicer_to_server,
                preferences_service,
                preferences_services_pb2.DESCRIPTOR.services_by_name["Preferences"],
            )
        )

        providers_service = ProvidersService(database, looper)
        self._servicers.append(
            (
                providers_services_pb2_grpc.add_ProvidersServicer_to_server,
                providers_service,
                providers_services_pb2.DESCRIPTOR.services_by_name["Providers"],
            )
        )

        llm_models_service = LlmModelsService(database, looper)
        self._servicers.append(
            (
                llm_models_services_pb2_grpc.add_LlmModelsServicer_to_server,
                llm_models_service,
                llm_models_services_pb2.DESCRIPTOR.services_by_name["LlmModels"],
            )
        )

        agents_service = AgentsService(database, gateways)
        self._servicers.append(
            (
                agents_services_pb2_grpc.add_AgentsServicer_to_server,
                agents_service,
                agents_services_pb2.DESCRIPTOR.services_by_name["Agents"],
            )
        )

        bricks_service = BricksService(database, looper)
        self._servicers.append(
            (
                bricks_services_pb2_grpc.add_BricksServicer_to_server,
                bricks_service,
                bricks_services_pb2.DESCRIPTOR.services_by_name["Bricks"],
            )
        )

        gateways_service = GatewaysService(database, gateways)
        self._servicers.append(
            (
                gateways_services_pb2_grpc.add_GatewaysServicer_to_server,
                gateways_service,
                gateways_services_pb2.DESCRIPTOR.services_by_name["Gateways"],
            )
        )

        conversations_service = ConversationsService(database, looper)
        self._servicers.append(
            (
                conversations_services_pb2_grpc.add_ConversationsServicer_to_server,
                conversations_service,
                conversations_services_pb2.DESCRIPTOR.services_by_name["Conversations"],
            )
        )

        messages_service = MessagesService(database, looper)
        self._servicers.append(
            (
                messages_services_pb2_grpc.add_MessagesServicer_to_server,
                messages_service,
                messages_services_pb2.DESCRIPTOR.services_by_name["Messages"],
            )
        )

        blob_service = BlobService(blob)
        self._servicers.append(
            (
                blob_services_pb2_grpc.add_BlobsServicer_to_server,
                blob_service,
                blob_services_pb2.DESCRIPTOR.services_by_name["Blobs"],
            )
        )

        self._logger.debug("server_initialized", service_count=len(self._servicers))

    async def run(self, port: int, host: str, enable_reflection: bool) -> None:
        """Start the gRPC server and block until termination.

        Args:
            port: Port number to bind to.
            host: Host address to bind to.
            enable_reflection: Enable gRPC server reflection for service discovery.
        """
        self._server = grpc.aio.server()

        for add_servicer_fn, servicer, service_descriptor in self._servicers:
            add_servicer_fn(servicer, self._server)
            self._logger.debug("service_registered", service=service_descriptor.full_name)

        if enable_reflection:
            service_descriptors = tuple(s[2] for s in self._servicers)
            service_names = tuple(d.full_name for d in service_descriptors)
            self._logger.debug("enabling_reflection", service_names=service_names)
            reflection.enable_server_reflection(service_names, self._server)

        self._server.add_insecure_port(f"{host}:{port}")

        self._logger.info("server_starting", host=host, port=port, reflection=enable_reflection)
        await self._server.start()

        await self._server.wait_for_termination()

    async def stop(self, grace_period: float = 5.0) -> None:
        """Stop the server gracefully with optional grace period.

        Args:
            grace_period: Seconds to wait for active RPCs to complete.
        """
        if self._server:
            self._logger.info("server_stopping", grace_period=grace_period)
            await self._server.stop(grace_period)
            self._logger.info("server_stopped_successfully")
