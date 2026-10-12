from typing import Annotated, Union
from sqlmodel import Field
from pydantic import Discriminator
from ..base import Base
from ..types import ModelJSON
from .preference_key import PreferenceKey
from .preference_value_string import PreferenceValueString
from .preference_value_int import PreferenceValueInt
from .preference_value_float import PreferenceValueFloat
from .preference_value_bool import PreferenceValueBool

PreferenceValue = Annotated[
    Union[
        PreferenceValueString,
        PreferenceValueInt,
        PreferenceValueFloat,
        PreferenceValueBool,
    ],
    Discriminator("type"),
]


class Preference(Base, table=True):
    """User preference storage."""

    __tablename__ = "preferences"

    key: PreferenceKey = Field(unique=True)
    value: PreferenceValue = Field(sa_type=ModelJSON(PreferenceValue))
