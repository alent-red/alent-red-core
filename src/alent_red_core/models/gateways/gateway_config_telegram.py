from typing import Literal

from pydantic import BaseModel

from ..types import TelegramUsernameStr, TrimmedNonEmptyStr
from .gateway_config_type import GatewayConfigType


class GatewayConfigTelegram(BaseModel):
    """Configuration for Telegram gateway."""

    type: Literal[GatewayConfigType.TELEGRAM] = GatewayConfigType.TELEGRAM
    token: TrimmedNonEmptyStr
    allow_all: bool
    allowed_user_names: list[TelegramUsernameStr]
