from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigVision(BaseModel):
    """Configuration for vision brick."""

    type: Literal[BrickConfigType.VISION] = BrickConfigType.VISION
