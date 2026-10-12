from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigBrowser(BaseModel):
    """Configuration for browser brick."""

    type: Literal[BrickConfigType.BROWSER] = BrickConfigType.BROWSER
