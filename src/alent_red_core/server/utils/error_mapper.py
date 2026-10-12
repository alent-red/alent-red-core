import grpc

from ...models import Error, ErrorCode


def map_exception_to_error(
    exception: Exception,
) -> tuple[grpc.StatusCode, ErrorCode, str | None]:
    """Map exception to gRPC status code, error code, and optional message text.

    Only text written by our own Error exceptions is exposed; for any other
    exception, the message is None to avoid leaking server-side details.

    Args:
        exception: The exception to map.

    Returns:
        Tuple of (grpc.StatusCode, ErrorCode, error message text or None).
    """
    if isinstance(exception, Error):
        return (grpc.StatusCode.UNKNOWN, exception.code, str(exception))

    if isinstance(exception, ValueError):
        return (grpc.StatusCode.UNKNOWN, ErrorCode.INVALID_ARGUMENT, None)

    return (grpc.StatusCode.UNKNOWN, ErrorCode.INTERNAL, None)
