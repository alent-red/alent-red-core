from .models import Key, MouseButton, PointerPosition, Screen, ScreenCapture


class BaseSystemAccess:
    """Base class for OS-specific system access implementations.

    System access exposes raw OS primitives (screen enumeration,
    screenshot, keyboard input). Higher-level policy (resize, encoding,
    inter-key delay, blob storage) lives in the brick.
    """

    @property
    def allowed_keys(self) -> set[Key]:
        """Get the set of keys supported on this host operating system.

        Returns:
            Subset of Key values that the implementation can produce.
        """
        raise NotImplementedError

    async def list_screens(self) -> list[Screen]:
        """Enumerate connected displays.

        Returns:
            List of Screen entries; id is 1-based and stable across
            calls within a session.

        Raises:
            Error: If the host operating system is not supported.
        """
        raise NotImplementedError

    async def capture_screen(self, screen_id: int) -> ScreenCapture:
        """Capture one display as a raw BGRA pixel buffer (cursor excluded).

        Args:
            screen_id: 1-based identifier returned by list_screens.

        Returns:
            ScreenCapture with raw BGRA bytes, width and height.

        Raises:
            Error: If the screen id is out of range or capture fails.
        """
        raise NotImplementedError

    async def get_pointer_position(self, screen_id: int) -> PointerPosition | None:
        """Get the pointer position in pixels within the given screen.

        Args:
            screen_id: 1-based identifier returned by list_screens.

        Returns:
            PointerPosition with x, y in screen-local pixels (top-left
            origin) if the pointer is currently inside the screen, or
            None if the pointer is on a different display.

        Raises:
            Error: If the screen id is out of range or the query fails.
        """
        raise NotImplementedError

    async def click_pointer(self, button: MouseButton, count: int, event_tag: int) -> None:
        """Click the given mouse button at the current pointer position.

        Args:
            button: Which mouse button to click.
            count: Number of clicks (1 = single, 2 = double, 3 = triple).
                Must be >= 1.
            event_tag: Magic integer written to the OS event's user-data
                field (kCGEventSourceUserData on macOS, dwExtraInfo on
                Windows) so an overlay sitting in front of other windows
                can recognize and pass through synthetic events from
                this process.

        Raises:
            Error: If count is invalid or the click fails.
        """
        raise NotImplementedError

    async def move_pointer(self, screen_id: int, x: int, y: int) -> None:
        """Smoothly move the pointer to a position on the given screen.

        Coordinates are in the same pixel space as ScreenCapture and
        PointerPosition (top-left origin, rendered pixel space).
        Implementations animate the movement with an ease-in-out
        interpolation over ~500ms.

        Args:
            screen_id: 1-based identifier returned by list_screens.
            x: Target x in screen-local pixels (top-left origin).
            y: Target y in screen-local pixels (top-left origin).

        Raises:
            Error: If the screen id is out of range or the move fails.
        """
        raise NotImplementedError

    async def tap_key(self, key: Key, event_tag: int) -> None:
        """Press and release a single key, layout-aware for character keys.

        Args:
            key: Key identifier; must be in allowed_keys.
            event_tag: Magic integer written to the OS event's user-data
                field so an overlay can recognize and pass through
                synthetic events from this process.

        Raises:
            Error: If the key is not in allowed_keys or cannot be
                produced on the current keyboard layout.
        """
        raise NotImplementedError

    async def press_keys_together(self, keys: list[Key], event_tag: int) -> None:
        """Press all keys down then release them in reverse order.

        Used for modifier + key shortcuts. Translation is layout-aware
        for character keys.

        Args:
            keys: Ordered list of keys; first listed is pressed first
                and released last.
            event_tag: Magic integer written to the OS event's user-data
                field so an overlay can recognize and pass through
                synthetic events from this process.

        Raises:
            Error: If any key is not in allowed_keys or cannot be
                produced on the current keyboard layout.
        """
        raise NotImplementedError

    async def type_text(self, text: str, event_tag: int) -> None:
        """Type a literal Unicode string, layout-independent.

        Args:
            text: Text to type.
            event_tag: Magic integer written to the OS event's user-data
                field so an overlay can recognize and pass through
                synthetic events from this process.

        Raises:
            Error: If injection fails.
        """
        raise NotImplementedError
