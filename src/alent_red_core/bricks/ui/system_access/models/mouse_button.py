from enum import Enum


class MouseButton(str, Enum):
    """Which mouse button to operate on."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"
