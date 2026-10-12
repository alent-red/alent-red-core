import os
import grpc.aio
from ...generated.proto.info import messages_pb2, services_pb2_grpc
from ...common import Logger
from ..utils import handle_grpc_errors


class InfoService(services_pb2_grpc.InfoServicer):
    """Info service implementation."""

    def __init__(self, version: str):
        """Initialize the info service.

        Args:
            version: Application version string.
        """
        self._version = version
        self._logger = Logger.get_logger("server.services.info")

    @handle_grpc_errors
    async def GetInfo(
        self,
        request: messages_pb2.GetInfoRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.GetInfoRequest, messages_pb2.GetInfoResponse
        ],
    ) -> messages_pb2.GetInfoResponse:
        pid = os.getpid()

        self._logger.debug("get_info_called", version=self._version, pid=pid)

        return messages_pb2.GetInfoResponse(version=self._version, pid=pid)
