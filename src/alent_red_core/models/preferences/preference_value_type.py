from enum import Enum


class PreferenceValueType(str, Enum):
    """Preference value types."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
