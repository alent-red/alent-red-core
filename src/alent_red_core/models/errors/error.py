from .error_code import ErrorCode


class Error(Exception):
    """Base error for ALENT.RED Core."""

    def __init__(self, code: ErrorCode, message: str):
        """Initialize error.

        Args:
            code: Error code.
            message: Error message.
        """
        self.code = code
        super().__init__(message)
