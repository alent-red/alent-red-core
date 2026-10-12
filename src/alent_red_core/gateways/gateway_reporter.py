from abc import ABC, abstractmethod
from uuid import UUID

from ..models import ConversationSender, Error, MessageContentUser


class GatewayReporter(ABC):
    """Interface a gateway uses to report events back to the manager.

    A gateway is given its own identifier and reports events with it, so the
    manager can route each event to the correct gateway.
    """

    @abstractmethod
    async def handle_message(
        self,
        gateway_id: UUID,
        gateway_external_id: str,
        content: MessageContentUser,
        sender: ConversationSender,
    ) -> None:
        """Report a new user message from a gateway.

        Args:
            gateway_id: Identifier of the gateway the message originates from.
            gateway_external_id: External identifier of the conversation on the gateway.
            content: The user message content.
            sender: Identity of the sender on the gateway.
        """
        pass

    @abstractmethod
    async def handle_error(self, gateway_id: UUID, error: Error | None) -> None:
        """Report a gateway-level error, or clear it when recovered.

        Args:
            gateway_id: Identifier of the gateway reporting the error.
            error: Error that occurred on the gateway, or None to clear it.
        """
        pass
