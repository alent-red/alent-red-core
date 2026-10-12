from typing import Literal

from pydantic import BaseModel

from .brick_config_type import BrickConfigType


class BrickConfigSkills(BaseModel):
    """Configuration for skills brick."""

    type: Literal[BrickConfigType.SKILLS] = BrickConfigType.SKILLS
