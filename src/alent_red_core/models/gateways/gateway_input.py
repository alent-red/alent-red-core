from uuid import UUID
from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from ..errors import ErrorCode
from .gateway_config_telegram import GatewayConfigTelegram


class GatewayInput(BaseModel):
    """Gateway input."""

    name: TrimmedNonEmptyStr
    send_detailed_messages: bool
    error_code: ErrorCode | None
    error_message: TrimmedNonEmptyStr | None
    config: GatewayConfigTelegram
    agent_id: UUID
