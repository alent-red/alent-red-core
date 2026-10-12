from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigRenderer(BaseModel):
    """Configuration for renderer brick."""

    type: Literal[BrickConfigType.RENDERER] = BrickConfigType.RENDERER
