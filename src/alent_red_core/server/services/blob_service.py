import grpc

from ...common import Logger
from ...generated.proto.blob import services_pb2_grpc, messages_pb2
from ...blob import BlobStorage
from ...models import Blob, Error, ErrorCode
from ..utils import handle_grpc_errors


class BlobService(services_pb2_grpc.BlobsServicer):
    """Blob storage service."""

    def __init__(self, blob: BlobStorage):
        """Initialize blob service.

        Args:
            blob: Blob storage instance.
        """
        self._blob = blob
        self._logger = Logger.get_logger("server.services.blob")

    @handle_grpc_errors
    async def Save(
        self,
        request: messages_pb2.SaveBlobRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.SaveBlobRequest, messages_pb2.SaveBlobResponse
        ],
    ) -> messages_pb2.SaveBlobResponse:
        """Save blob to encrypted storage."""
        self._logger.debug(
            "save_called",
            content_type=request.blob.content_type,
            file_name=request.blob.file_name if request.blob.HasField("file_name") else None,
        )

        blob = Blob(
            content=request.blob.content,
            content_type=request.blob.content_type,
            file_name=request.blob.file_name if request.blob.HasField("file_name") else None,
        )

        key = await self._blob.save(blob)

        self._logger.debug("save_completed", key=key)

        return messages_pb2.SaveBlobResponse(key=key)

    @handle_grpc_errors
    async def Read(
        self,
        request: messages_pb2.ReadBlobRequest,
        context: grpc.aio.ServicerContext[
            messages_pb2.ReadBlobRequest, messages_pb2.ReadBlobResponse
        ],
    ) -> messages_pb2.ReadBlobResponse:
        """Read and decrypt blob by key."""
        self._logger.debug("read_called", key=request.key)

        blob = await self._blob.read(request.key)

        if blob is None:
            raise Error(ErrorCode.NOT_FOUND, "Blob not found")

        self._logger.debug("read_completed", key=request.key)

        return messages_pb2.ReadBlobResponse(blob=self._python_blob_to_proto(blob))

    def _python_blob_to_proto(self, python_blob: Blob) -> messages_pb2.Blob:
        """Convert Python Blob to proto Blob."""
        proto_blob = messages_pb2.Blob(
            content=python_blob.content,
            content_type=python_blob.content_type,
        )

        if python_blob.file_name is not None:
            proto_blob.file_name = python_blob.file_name

        return proto_blob
