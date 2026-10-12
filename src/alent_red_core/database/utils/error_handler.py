from functools import wraps
from typing import TypeVar, Callable, Awaitable, ParamSpec
from ...models import Error
from .error_mapper import map_exception_to_error

P = ParamSpec("P")
R = TypeVar("R")


def handle_database_errors(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Decorator to handle database exceptions in store methods.

    Maps exceptions to custom Error with appropriate ErrorCode.
    Re-raises custom Error exceptions as-is.

    Args:
        func: The async store method to wrap.

    Returns:
        Wrapped async function with error handling.
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except Error:
            # Re-raise custom errors as-is
            raise
        except Exception as e:
            # Map exception to ErrorCode and raise custom Error
            error_code = map_exception_to_error(e)
            raise Error(error_code, f"Database operation failed: {type(e).__name__}")

    return wrapper
