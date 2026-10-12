from typing import TYPE_CHECKING, Annotated, Union
from sqlmodel import Field, Relationship
from pydantic import Discriminator

from ..base import Base
from ..types import ModelJSON, TrimmedNonEmptyStr
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

if TYPE_CHECKING:
    from ..agent_bricks import AgentBrick

BrickConfig = Annotated[
    Union[
        BrickConfigUI,
        BrickConfigCode,
        BrickConfigVision,
        BrickConfigSkills,
        BrickConfigCustom,
        BrickConfigSystem,
        BrickConfigScheduler,
        BrickConfigRenderer,
        BrickConfigBrowser,
        BrickConfigAgent,
    ],
    Discriminator("type"),
]


class Brick(Base, table=True):
    """Brick entity."""

    name: TrimmedNonEmptyStr = Field(unique=True)
    config: BrickConfig = Field(sa_type=ModelJSON(BrickConfig))

    agent_bricks: list["AgentBrick"] = Relationship(
        back_populates="brick",
        sa_relationship_kwargs={"passive_deletes": True},
    )
