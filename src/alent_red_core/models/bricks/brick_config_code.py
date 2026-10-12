from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigCode(BaseModel):
    """Configuration for code brick."""

    type: Literal[BrickConfigType.CODE] = BrickConfigType.CODE
