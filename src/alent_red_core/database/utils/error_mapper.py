from sqlalchemy.exc import IntegrityError
from ...models import Error, ErrorCode


def map_exception_to_error(exception: Exception) -> ErrorCode:
    """Map exception to ErrorCode.

    Args:
        exception: The exception to map.

    Returns:
        ErrorCode for the exception.
    """
    if isinstance(exception, Error):
        return exception.code

    if isinstance(exception, ValueError):
        return ErrorCode.INVALID_ARGUMENT

    if isinstance(exception, IntegrityError):
        error_message = str(exception.orig) if hasattr(exception, "orig") else str(exception)

        if (
            "UNIQUE constraint failed" in error_message
            or "unique constraint" in error_message.lower()
        ):
            return ErrorCode.DUPLICATED

        if (
            "FOREIGN KEY constraint failed" in error_message
            or "foreign key" in error_message.lower()
        ):
            return ErrorCode.RELATION_VIOLATION

        if "NOT NULL constraint failed" in error_message or "not null" in error_message.lower():
            return ErrorCode.INVALID_ARGUMENT

        return ErrorCode.INTERNAL

    return ErrorCode.INTERNAL
