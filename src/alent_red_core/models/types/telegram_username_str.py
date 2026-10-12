import re
from typing import Annotated
from pydantic import AfterValidator

_TELEGRAM_USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{5,32}$")


def validate_telegram_username(v: str) -> str:
    """Validates that string is a canonical Telegram username.

    The client is responsible for canonicalizing (stripping the leading "@",
    lowercasing, trimming) before sending. We only accept the canonical form:
    5 to 32 characters of lowercase letters, digits, and underscores.

    Args:
        v: String value to validate.

    Returns:
        The validated string.

    Raises:
        ValueError: If string is not a canonical Telegram username.
    """
    if _TELEGRAM_USERNAME_PATTERN.fullmatch(v) is None:
        raise ValueError(
            "must be a canonical Telegram username (5-32 lowercase letters, digits, underscores)"
        )
    return v


TelegramUsernameStr = Annotated[str, AfterValidator(validate_telegram_username)]
