from enum import Enum


class GatewayConfigType(str, Enum):
    """Gateway configuration type enumeration."""

    TELEGRAM = "telegram"
