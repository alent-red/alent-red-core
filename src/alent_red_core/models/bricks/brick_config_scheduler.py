from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigScheduler(BaseModel):
    """Configuration for scheduler brick."""

    type: Literal[BrickConfigType.SCHEDULER] = BrickConfigType.SCHEDULER
