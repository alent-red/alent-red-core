from ..models import Gateway, GatewayConfigType, Error, ErrorCode
from ..blob import BlobStorage
from .base_gateway import BaseGateway
from .gateway_reporter import GatewayReporter
from .telegram import TelegramGateway


class GatewayBuilder:
    """Factory for building gateway instances."""

    @staticmethod
    async def build(gateway: Gateway, blob: BlobStorage, reporter: GatewayReporter) -> BaseGateway:
        """Build gateway instance for specified gateway configuration.

        Args:
            gateway: Gateway configuration from database.
            blob: Blob storage instance.
            reporter: Reporter interface to report events back to the manager.

        Returns:
            Initialized and setup gateway instance.

        Raises:
            Error: If gateway type is not supported.
        """
        config = gateway.config

        if config.type == GatewayConfigType.TELEGRAM:
            instance: BaseGateway = TelegramGateway(config, blob, gateway.id, reporter)
            await instance.setup()
            return instance
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported gateway type: {config.type}")
