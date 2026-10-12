from pydantic import BaseModel
from .preference_key import PreferenceKey
from .preference_value_string import PreferenceValueString
from .preference_value_int import PreferenceValueInt
from .preference_value_float import PreferenceValueFloat
from .preference_value_bool import PreferenceValueBool
from .preference import PreferenceValue


class PreferenceInput(BaseModel):
    """Preference input."""

    key: PreferenceKey
    value: PreferenceValue
