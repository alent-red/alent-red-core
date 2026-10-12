from enum import Enum


class PressKind(str, Enum):
    """How to press a sequence of keys."""

    SUCCESSIVE = "SUCCESSIVE"
    SAME_TIME = "SAME_TIME"
