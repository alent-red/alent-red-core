from abc import ABC
from uuid import UUID

from ..models import Error, GatewayConfig
from ..blob import BlobStorage
from .gateway_reporter import GatewayReporter


class BaseGateway(ABC):
    """Base class for all gateways.

    Gateways are global instances initialized once and used across conversations.
    """

    def __init__(
        self,
        config: GatewayConfig,
        blob: BlobStorage,
        gateway_id: UUID,
        reporter: GatewayReporter,
    ):
        """Initialize gateway.

        Args:
            config: Gateway configuration.
            blob: Blob storage instance.
            gateway_id: Identifier of this gateway.
            reporter: Reporter interface to report events back to the manager.
        """
        self._config = config
        self._blob = blob
        self._gateway_id = gateway_id
        self._reporter = reporter

    async def setup(self) -> None:
        """Setup gateway resources. Override in subclasses if needed."""
        pass

    async def refresh(self, config: GatewayConfig) -> None:
        """Refresh gateway resources. Override in subclasses if needed.

        Args:
            config: Updated gateway configuration.
        """
        self._config = config

    async def clean(self) -> None:
        """Clean gateway resources. Override in subclasses if needed."""
        pass

    async def handle_conversation_processing(
        self, gateway_external_id: str, processing: bool
    ) -> None:
        """Handle a conversation processing state change. Override if needed.

        Args:
            gateway_external_id: External identifier of the conversation on the gateway.
            processing: Whether the conversation is currently processing.
        """
        pass

    async def handle_conversation_error(self, gateway_external_id: str, error: Error) -> None:
        """Handle a conversation error. Override if needed.

        Args:
            gateway_external_id: External identifier of the conversation on the gateway.
            error: Error that occurred while processing the conversation.
        """
        pass

    async def handle_message(
        self, gateway_external_id: str, text: str | None, image_file_keys: list[str]
    ) -> None:
        """Handle a message rendered by the manager. Override if needed.

        Args:
            gateway_external_id: External identifier of the conversation on the gateway.
            text: Rendered text to send, or None when only images are sent.
            image_file_keys: Blob keys of images to send.
        """
        pass
