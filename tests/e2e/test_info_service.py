import os

import grpc

from alent_red_core import __version__
from alent_red_core.generated.proto.info import messages_pb2, services_pb2_grpc


class TestInfoService:
    """E2E tests for the Info service."""

    async def test_get_info_returns_current_version_and_process_pid(
        self, channel: grpc.aio.Channel
    ) -> None:
        """GetInfo should return the package's __version__ and the server process's PID."""
        stub = services_pb2_grpc.InfoStub(channel)  # type: ignore[no-untyped-call]

        response = await stub.GetInfo(messages_pb2.GetInfoRequest())

        assert response.version == __version__
        assert response.pid == os.getpid()
