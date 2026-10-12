from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr
from .brick_config_ui import BrickConfigUI
from .brick_config_code import BrickConfigCode
from .brick_config_vision import BrickConfigVision
from .brick_config_skills import BrickConfigSkills
from .brick_config_custom import BrickConfigCustom
from .brick_config_system import BrickConfigSystem
from .brick_config_scheduler import BrickConfigScheduler
from .brick_config_renderer import BrickConfigRenderer
from .brick_config_browser import BrickConfigBrowser
from .brick_config_agent import BrickConfigAgent


class BrickInput(BaseModel):
    """Brick input."""

    name: TrimmedNonEmptyStr
    config: (
        BrickConfigUI
        | BrickConfigCode
        | BrickConfigVision
        | BrickConfigSkills
        | BrickConfigCustom
        | BrickConfigSystem
        | BrickConfigScheduler
        | BrickConfigRenderer
        | BrickConfigBrowser
        | BrickConfigAgent
    )
