from typing import Annotated
from pydantic import AfterValidator


def validate_trimmed_non_empty(v: str) -> str:
    """Validates that string is trimmed and non-empty.

    Args:
        v: String value to validate.

    Returns:
        The validated string.

    Raises:
        ValueError: If string is not trimmed or is empty.
    """
    if v != v.strip(" "):
        raise ValueError("must be trimmed (no leading/trailing spaces)")
    if len(v) == 0:
        raise ValueError("must not be empty")
    return v


TrimmedNonEmptyStr = Annotated[str, AfterValidator(validate_trimmed_non_empty)]
