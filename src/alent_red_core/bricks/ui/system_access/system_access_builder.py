import platform

from ....models import Error, ErrorCode
from .base_system_access import BaseSystemAccess
from .implementations import MacosSystemAccess, WindowsSystemAccess


class SystemAccessBuilder:
    """Factory for building the OS-specific SystemAccess instance."""

    _os_darwin = "Darwin"
    _os_windows = "Windows"

    @staticmethod
    async def build() -> BaseSystemAccess:
        """Build the SystemAccess implementation for the host operating system.

        Returns:
            BaseSystemAccess implementation for the current OS.

        Raises:
            Error: If the host operating system is not supported.
        """
        os_name = platform.system()
        if os_name == SystemAccessBuilder._os_darwin:
            return MacosSystemAccess()
        elif os_name == SystemAccessBuilder._os_windows:
            return WindowsSystemAccess()
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported OS: {os_name}")
