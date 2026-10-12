from typing import Literal

from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from .brick_config_type import BrickConfigType


class BrickConfigCustom(BaseModel):
    """Configuration for custom brick."""

    type: Literal[BrickConfigType.CUSTOM] = BrickConfigType.CUSTOM
    path: TrimmedNonEmptyStr
