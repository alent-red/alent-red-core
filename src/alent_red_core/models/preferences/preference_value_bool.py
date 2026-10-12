from typing import Literal
from pydantic import BaseModel
from .preference_value_type import PreferenceValueType


class PreferenceValueBool(BaseModel):
    """Boolean preference value."""

    type: Literal[PreferenceValueType.BOOL] = PreferenceValueType.BOOL
    value: bool
