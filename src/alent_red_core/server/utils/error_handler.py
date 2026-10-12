from functools import wraps
from typing import TypeVar, Callable, Awaitable, ParamSpec, cast
import grpc
import grpc.aio
from .error_mapper import map_exception_to_error

P = ParamSpec("P")
R = TypeVar("R")


def handle_grpc_errors(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Decorator to handle exceptions in gRPC service methods.

    Maps Python exceptions to gRPC errors with custom error codes in metadata.
    Returns empty response after abort for type checking (never reached).

    Args:
        func: The async service method to wrap.

    Returns:
        Wrapped async function with error handling.
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except Exception as exception:
            context_obj: object = args[2] if len(args) > 2 else kwargs.get("context")

            if context_obj is None:
                raise RuntimeError("gRPC context not found in method arguments")

            if not hasattr(context_obj, "abort"):
                raise RuntimeError("Invalid gRPC context: missing abort method")

            context = cast("grpc.aio.ServicerContext[object, object]", context_obj)

            status_code, error_code, error_message = map_exception_to_error(exception)

            trailing_metadata: tuple[tuple[str, str], ...] = (("error-code", error_code.value),)
            if error_message is not None:
                trailing_metadata = trailing_metadata + (("error-message", error_message),)

            await context.abort(
                code=status_code,
                details="Operation failed",
                trailing_metadata=trailing_metadata,
            )

            return_type = func.__annotations__.get("return")
            if return_type is not None:
                return cast(R, return_type())
            raise

    return wrapper
