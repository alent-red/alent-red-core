from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from .brick_config_type import BrickConfigType
from .brick_config_ui_move_pointer_coordinate_space import BrickConfigUIMovePointerCoordinateSpace
from .brick_config_ui_move_pointer_geometry import BrickConfigUIMovePointerGeometry


class BrickConfigUI(BaseModel):
    """Configuration for UI brick."""

    type: Literal[BrickConfigType.UI] = BrickConfigType.UI
    move_pointer_llm_model_id: UUID
    move_pointer_geometry: BrickConfigUIMovePointerGeometry
    move_pointer_coordinate_space: BrickConfigUIMovePointerCoordinateSpace
