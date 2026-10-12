from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigSystem(BaseModel):
    """Configuration for system brick."""

    type: Literal[BrickConfigType.SYSTEM] = BrickConfigType.SYSTEM
