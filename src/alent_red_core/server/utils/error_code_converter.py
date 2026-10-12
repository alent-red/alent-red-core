from ...generated.proto.common import errors_pb2
from ...models import Error, ErrorCode


def python_error_code_to_proto(python_error_code: ErrorCode) -> errors_pb2.ErrorCode:
    """Convert Python ErrorCode enum to proto ErrorCode enum.

    Args:
        python_error_code: Python ErrorCode value.

    Returns:
        Proto ErrorCode enum value.

    Raises:
        Error: If the ErrorCode value has no proto mapping.
    """
    if python_error_code == ErrorCode.UNKNOWN:
        return errors_pb2.ERROR_CODE_UNKNOWN
    elif python_error_code == ErrorCode.INTERNAL:
        return errors_pb2.ERROR_CODE_INTERNAL
    elif python_error_code == ErrorCode.INVALID_ARGUMENT:
        return errors_pb2.ERROR_CODE_INVALID_ARGUMENT
    elif python_error_code == ErrorCode.NOT_SUPPORTED:
        return errors_pb2.ERROR_CODE_NOT_SUPPORTED
    elif python_error_code == ErrorCode.NOT_ALLOWED:
        return errors_pb2.ERROR_CODE_NOT_ALLOWED
    elif python_error_code == ErrorCode.NOT_FOUND:
        return errors_pb2.ERROR_CODE_NOT_FOUND
    elif python_error_code == ErrorCode.DUPLICATED:
        return errors_pb2.ERROR_CODE_DUPLICATED
    elif python_error_code == ErrorCode.RELATION_VIOLATION:
        return errors_pb2.ERROR_CODE_RELATION_VIOLATION
    elif python_error_code == ErrorCode.RATE_LIMIT:
        return errors_pb2.ERROR_CODE_RATE_LIMIT
    elif python_error_code == ErrorCode.INVALID_RESPONSE:
        return errors_pb2.ERROR_CODE_INVALID_RESPONSE
    elif python_error_code == ErrorCode.TIMEOUT:
        return errors_pb2.ERROR_CODE_TIMEOUT
    else:
        raise Error(ErrorCode.NOT_SUPPORTED, f"Unknown error code: {python_error_code}")
