from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigAgent(BaseModel):
    """Configuration for agent brick."""

    type: Literal[BrickConfigType.AGENT] = BrickConfigType.AGENT
