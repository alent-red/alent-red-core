from typing import Annotated
from pydantic import AfterValidator, HttpUrl, TypeAdapter

_http_url_adapter = TypeAdapter(HttpUrl)


def validate_url(value: str) -> str:
    """Validates that string is a syntactically valid HTTP/HTTPS URL.

    Uses Pydantic's HttpUrl parser to validate the format but returns the
    original string unchanged (no normalization, no trailing-slash addition).

    Args:
        value: String value to validate.

    Returns:
        The validated string, unchanged.

    Raises:
        ValueError: If string is not a valid HTTP/HTTPS URL.
    """
    _http_url_adapter.validate_python(value)
    return value


UrlStr = Annotated[str, AfterValidator(validate_url)]
