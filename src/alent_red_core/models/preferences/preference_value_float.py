from typing import Literal
from pydantic import BaseModel
from .preference_value_type import PreferenceValueType


class PreferenceValueFloat(BaseModel):
    """Float preference value."""

    type: Literal[PreferenceValueType.FLOAT] = PreferenceValueType.FLOAT
    value: float
