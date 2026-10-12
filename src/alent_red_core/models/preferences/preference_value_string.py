from typing import Literal
from pydantic import BaseModel
from ..types import TrimmedNonEmptyStr
from .preference_value_type import PreferenceValueType


class PreferenceValueString(BaseModel):
    """String preference value."""

    type: Literal[PreferenceValueType.STRING] = PreferenceValueType.STRING
    value: TrimmedNonEmptyStr
