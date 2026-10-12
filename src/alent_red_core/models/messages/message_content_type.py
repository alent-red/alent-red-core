from enum import Enum


class MessageContentType(str, Enum):
    """Message content type."""

    INTERNAL = "INTERNAL"
    USER = "USER"
    AI = "AI"
    TOOL = "TOOL"
