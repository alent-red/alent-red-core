from typing import Literal
from pydantic import BaseModel
from .preference_value_type import PreferenceValueType


class PreferenceValueInt(BaseModel):
    """Integer preference value."""

    type: Literal[PreferenceValueType.INT] = PreferenceValueType.INT
    value: int
