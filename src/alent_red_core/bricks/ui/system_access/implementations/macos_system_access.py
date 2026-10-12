"""macOS implementation of SystemAccess using ctypes.

All Apple-framework calls live in this module. The class exposes the
same interface as BaseSystemAccess; higher-level code (UIBrick) never
touches ctypes.
"""

import asyncio
import ctypes
import sys
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_bool,
    c_char_p,
    c_double,
    c_int32,
    c_int64,
    c_uint8,
    c_uint16,
    c_uint32,
    c_uint64,
    c_void_p,
)

from .....common import Logger
from .....models import Error, ErrorCode
from ..base_system_access import BaseSystemAccess
from ..models import Key, MouseButton, PointerPosition, Screen, ScreenCapture

_APPLICATION_SERVICES_PATH = (
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
_CORE_FOUNDATION_PATH = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
_CARBON_PATH = "/System/Library/Frameworks/Carbon.framework/Carbon"


_CG_HID_EVENT_TAP = 0
_UC_KEY_ACTION_DOWN = 0
_UC_KEY_TRANSLATE_NO_DEAD_KEYS_MASK = 1
_TIS_KEYBOARD_LAYOUT_DATA_PROPERTY = "TISPropertyUnicodeKeyLayoutData"
_CF_STRING_ENCODING_UTF8 = 0x08000100
_MAX_DISPLAYS = 32
_MAX_TYPED_CHARS = 4
_WINDOW_LIST_OPTION_ON_SCREEN_ONLY = 1
_NULL_WINDOW_ID = 0
_WINDOW_IMAGE_DEFAULT = 0

_CG_EVENT_FLAG_MASK_SHIFT = 0x00020000
_CG_EVENT_FLAG_MASK_CONTROL = 0x00040000
_CG_EVENT_FLAG_MASK_ALTERNATE = 0x00080000
_CG_EVENT_FLAG_MASK_COMMAND = 0x00100000

_CG_MOUSE_BUTTON_LEFT = 0
_CG_MOUSE_BUTTON_RIGHT = 1
_CG_EVENT_LEFT_MOUSE_DOWN = 1
_CG_EVENT_LEFT_MOUSE_UP = 2
_CG_EVENT_RIGHT_MOUSE_DOWN = 3
_CG_EVENT_RIGHT_MOUSE_UP = 4
_CG_EVENT_MOUSE_FIELD_CLICK_STATE = 1
_CG_EVENT_FIELD_SOURCE_USER_DATA = 42

_TYPE_TEXT_INTER_CHARACTER_DELAY_SECONDS = 0.002
_CLICK_INTER_CLICK_DELAY_SECONDS = 0.015

_MOVE_POINTER_TOTAL_DURATION_SECONDS = 0.5
_MOVE_POINTER_MIN_STEPS = 20
_MOVE_POINTER_MAX_STEPS = 60
_MOVE_POINTER_PIXELS_PER_STEP = 8
_MOVE_POINTER_JUMP_DISTANCE_POINTS = 5


_NON_CHARACTER_KEY_CODES: dict[Key, int] = {
    Key.CMD: 0x37,
    Key.OPTION: 0x3A,
    Key.CONTROL: 0x3B,
    Key.SHIFT: 0x38,
    Key.HOME: 0x73,
    Key.END: 0x77,
    Key.PAGE_UP: 0x74,
    Key.PAGE_DOWN: 0x79,
    Key.ARROW_UP: 0x7E,
    Key.ARROW_DOWN: 0x7D,
    Key.ARROW_LEFT: 0x7B,
    Key.ARROW_RIGHT: 0x7C,
    Key.F1: 0x7A,
    Key.F2: 0x78,
    Key.F3: 0x63,
    Key.F4: 0x76,
    Key.F5: 0x60,
    Key.F6: 0x61,
    Key.F7: 0x62,
    Key.F8: 0x64,
    Key.F9: 0x65,
    Key.F10: 0x6D,
    Key.F11: 0x67,
    Key.F12: 0x6F,
    Key.SPACE: 0x31,
    Key.TAB: 0x30,
    Key.ENTER: 0x24,
    Key.BACKSPACE: 0x33,
    Key.DELETE: 0x75,
    Key.ESCAPE: 0x35,
}


_MODIFIER_FLAG_MASKS: dict[Key, int] = {
    Key.CMD: _CG_EVENT_FLAG_MASK_COMMAND,
    Key.OPTION: _CG_EVENT_FLAG_MASK_ALTERNATE,
    Key.CONTROL: _CG_EVENT_FLAG_MASK_CONTROL,
    Key.SHIFT: _CG_EVENT_FLAG_MASK_SHIFT,
}


_CHARACTER_KEY_TO_CHAR: dict[Key, str] = {
    Key.A: "a",
    Key.B: "b",
    Key.C: "c",
    Key.D: "d",
    Key.E: "e",
    Key.F: "f",
    Key.G: "g",
    Key.H: "h",
    Key.I: "i",
    Key.J: "j",
    Key.K: "k",
    Key.L: "l",
    Key.M: "m",
    Key.N: "n",
    Key.O: "o",
    Key.P: "p",
    Key.Q: "q",
    Key.R: "r",
    Key.S: "s",
    Key.T: "t",
    Key.U: "u",
    Key.V: "v",
    Key.W: "w",
    Key.X: "x",
    Key.Y: "y",
    Key.Z: "z",
    Key.NUMBER_0: "0",
    Key.NUMBER_1: "1",
    Key.NUMBER_2: "2",
    Key.NUMBER_3: "3",
    Key.NUMBER_4: "4",
    Key.NUMBER_5: "5",
    Key.NUMBER_6: "6",
    Key.NUMBER_7: "7",
    Key.NUMBER_8: "8",
    Key.NUMBER_9: "9",
    Key.PUNCTUATION_EXCLAMATION_MARK: "!",
    Key.PUNCTUATION_QUESTION_MARK: "?",
    Key.PUNCTUATION_PERIOD: ".",
    Key.PUNCTUATION_COMMA: ",",
    Key.PUNCTUATION_SEMICOLON: ";",
    Key.PUNCTUATION_COLON: ":",
    Key.PUNCTUATION_SINGLE_QUOTE: "'",
    Key.PUNCTUATION_DOUBLE_QUOTE: '"',
    Key.PUNCTUATION_LEFT_PARENTHESIS: "(",
    Key.PUNCTUATION_RIGHT_PARENTHESIS: ")",
    Key.PUNCTUATION_LEFT_BRACKET: "[",
    Key.PUNCTUATION_RIGHT_BRACKET: "]",
    Key.PUNCTUATION_LEFT_BRACE: "{",
    Key.PUNCTUATION_RIGHT_BRACE: "}",
    Key.PUNCTUATION_PIPE: "|",
    Key.PUNCTUATION_SLASH: "/",
    Key.PUNCTUATION_AT_SIGN: "@",
    Key.PUNCTUATION_HASH: "#",
    Key.PUNCTUATION_DOLLAR_SIGN: "$",
    Key.PUNCTUATION_PERCENT_SIGN: "%",
    Key.PUNCTUATION_AMPERSAND: "&",
    Key.PUNCTUATION_ASTERISK: "*",
    Key.PUNCTUATION_PLUS: "+",
    Key.PUNCTUATION_MINUS: "-",
    Key.PUNCTUATION_EQUAL: "=",
    Key.PUNCTUATION_UNDERSCORE: "_",
    Key.PUNCTUATION_TILDE: "~",
    Key.PUNCTUATION_BACKTICK: "`",
}


_ALLOWED_KEYS: set[Key] = set(_NON_CHARACTER_KEY_CODES.keys()) | set(_CHARACTER_KEY_TO_CHAR.keys())


class _CGRect(Structure):
    _fields_ = [
        ("origin_x", c_double),
        ("origin_y", c_double),
        ("width", c_double),
        ("height", c_double),
    ]


class _CGPoint(Structure):
    _fields_ = [
        ("x", c_double),
        ("y", c_double),
    ]


if sys.platform == "darwin":
    _application_services = ctypes.CDLL(_APPLICATION_SERVICES_PATH)
    _core_foundation = ctypes.CDLL(_CORE_FOUNDATION_PATH)
    _carbon = ctypes.CDLL(_CARBON_PATH)

    _core_foundation.CFRelease.argtypes = [c_void_p]
    _core_foundation.CFRelease.restype = None
    _core_foundation.CFDataGetBytePtr.argtypes = [c_void_p]
    _core_foundation.CFDataGetBytePtr.restype = c_void_p
    _core_foundation.CFDataGetLength.argtypes = [c_void_p]
    _core_foundation.CFDataGetLength.restype = c_int32
    _core_foundation.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
    _core_foundation.CFStringCreateWithCString.restype = c_void_p

    _application_services.CGGetActiveDisplayList.argtypes = [
        c_uint32,
        POINTER(c_uint32),
        POINTER(c_uint32),
    ]
    _application_services.CGGetActiveDisplayList.restype = c_int32
    _application_services.CGMainDisplayID.argtypes = []
    _application_services.CGMainDisplayID.restype = c_uint32
    _application_services.CGDisplayBounds.argtypes = [c_uint32]
    _application_services.CGDisplayBounds.restype = _CGRect
    _application_services.CGDisplayCopyDisplayMode.argtypes = [c_uint32]
    _application_services.CGDisplayCopyDisplayMode.restype = c_void_p
    _application_services.CGDisplayModeGetPixelWidth.argtypes = [c_void_p]
    _application_services.CGDisplayModeGetPixelWidth.restype = c_uint64
    _application_services.CGDisplayModeRelease.argtypes = [c_void_p]
    _application_services.CGDisplayModeRelease.restype = None
    _application_services.CGEventCreate.argtypes = [c_void_p]
    _application_services.CGEventCreate.restype = c_void_p
    _application_services.CGEventGetLocation.argtypes = [c_void_p]
    _application_services.CGEventGetLocation.restype = _CGPoint
    _application_services.CGWindowListCreateImage.argtypes = [_CGRect, c_uint32, c_uint32, c_uint32]
    _application_services.CGWindowListCreateImage.restype = c_void_p
    _application_services.CGImageGetWidth.argtypes = [c_void_p]
    _application_services.CGImageGetWidth.restype = c_uint64
    _application_services.CGImageGetHeight.argtypes = [c_void_p]
    _application_services.CGImageGetHeight.restype = c_uint64
    _application_services.CGImageGetBytesPerRow.argtypes = [c_void_p]
    _application_services.CGImageGetBytesPerRow.restype = c_uint64
    _application_services.CGImageGetDataProvider.argtypes = [c_void_p]
    _application_services.CGImageGetDataProvider.restype = c_void_p
    _application_services.CGDataProviderCopyData.argtypes = [c_void_p]
    _application_services.CGDataProviderCopyData.restype = c_void_p
    _application_services.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint16, c_bool]
    _application_services.CGEventCreateKeyboardEvent.restype = c_void_p
    _application_services.CGEventPost.argtypes = [c_uint32, c_void_p]
    _application_services.CGEventPost.restype = None
    _application_services.CGEventSetFlags.argtypes = [c_void_p, c_uint64]
    _application_services.CGEventSetFlags.restype = None
    _application_services.CGEventCreateMouseEvent.argtypes = [
        c_void_p,
        c_uint32,
        _CGPoint,
        c_uint32,
    ]
    _application_services.CGEventCreateMouseEvent.restype = c_void_p
    _application_services.CGEventSetIntegerValueField.argtypes = [c_void_p, c_uint32, c_int64]
    _application_services.CGEventSetIntegerValueField.restype = None
    _application_services.CGWarpMouseCursorPosition.argtypes = [_CGPoint]
    _application_services.CGWarpMouseCursorPosition.restype = c_int32
    _application_services.CGAssociateMouseAndMouseCursorPosition.argtypes = [c_bool]
    _application_services.CGAssociateMouseAndMouseCursorPosition.restype = c_int32
    _application_services.CGEventKeyboardSetUnicodeString.argtypes = [
        c_void_p,
        c_uint64,
        POINTER(c_uint16),
    ]
    _application_services.CGEventKeyboardSetUnicodeString.restype = None

    _carbon.TISCopyCurrentKeyboardLayoutInputSource.argtypes = []
    _carbon.TISCopyCurrentKeyboardLayoutInputSource.restype = c_void_p
    _carbon.TISGetInputSourceProperty.argtypes = [c_void_p, c_void_p]
    _carbon.TISGetInputSourceProperty.restype = c_void_p
    _carbon.LMGetKbdType.argtypes = []
    _carbon.LMGetKbdType.restype = c_uint8
    _carbon.UCKeyTranslate.argtypes = [
        c_void_p,
        c_uint16,
        c_uint16,
        c_uint32,
        c_uint32,
        c_uint32,
        POINTER(c_uint32),
        c_uint64,
        POINTER(c_uint64),
        POINTER(c_uint16),
    ]
    _carbon.UCKeyTranslate.restype = c_int32


class MacosSystemAccess(BaseSystemAccess):
    """macOS implementation of SystemAccess using CoreGraphics and Carbon TIS."""

    def __init__(self) -> None:
        """Initialize macOS system access."""
        self._logger = Logger.get_logger(
            "bricks.ui.system_access.implementations.macos_system_access"
        )

    @property
    def allowed_keys(self) -> set[Key]:
        """Get the set of keys supported on macOS.

        Returns:
            All Key members the macOS implementation can produce.
        """
        return _ALLOWED_KEYS

    async def list_screens(self) -> list[Screen]:
        """Enumerate connected displays via CGGetActiveDisplayList.

        Returns:
            List of Screen entries; id is 1-based.

        Raises:
            Error: If called on a non-macOS host or enumeration fails.
        """
        self._logger.debug("list_screens_started")
        self._ensure_macos_host()
        screens = await asyncio.to_thread(self._list_screens)
        self._logger.debug("list_screens_completed", count=len(screens))
        return screens

    async def capture_screen(self, screen_id: int) -> ScreenCapture:
        """Capture one display as raw BGRA via CGWindowListCreateImage.

        Args:
            screen_id: 1-based identifier returned by list_screens.

        Returns:
            ScreenCapture with raw BGRA bytes, width and height.

        Raises:
            Error: If called on a non-macOS host, the screen id is out
                of range, or capture fails.
        """
        self._logger.debug("capture_screen_started", screen_id=screen_id)
        self._ensure_macos_host()
        capture = await asyncio.to_thread(self._capture_screen, screen_id)
        self._logger.debug(
            "capture_screen_completed",
            screen_id=screen_id,
            width=capture.width,
            height=capture.height,
            bgra_bytes=len(capture.bgra),
        )
        return capture

    async def get_pointer_position(self, screen_id: int) -> PointerPosition | None:
        """Resolve the pointer position via CGEventGetLocation.

        Args:
            screen_id: 1-based identifier returned by list_screens.

        Returns:
            PointerPosition in screen-local pixels if the pointer is on
            this screen, None otherwise.

        Raises:
            Error: If called on a non-macOS host, the screen id is out
                of range, or the query fails.
        """
        self._logger.debug("get_pointer_position_started", screen_id=screen_id)
        self._ensure_macos_host()
        position = await asyncio.to_thread(self._get_pointer_position, screen_id)
        self._logger.debug(
            "get_pointer_position_completed",
            screen_id=screen_id,
            x=position.x if position else None,
            y=position.y if position else None,
            on_screen=position is not None,
        )
        return position

    async def move_pointer(self, screen_id: int, x: int, y: int) -> None:
        """Smoothly move the pointer to a screen-local pixel position.

        Args:
            screen_id: 1-based identifier returned by list_screens.
            x: Target x in screen-local pixels (top-left origin).
            y: Target y in screen-local pixels (top-left origin).

        Raises:
            Error: If called on a non-macOS host, the screen id is out
                of range, or the move fails.
        """
        self._logger.debug("move_pointer_started", screen_id=screen_id, x=x, y=y)
        self._ensure_macos_host()
        target_point = await asyncio.to_thread(
            self._compute_target_point_in_global_space, screen_id, x, y
        )
        await self._smooth_move_pointer(target_point=target_point)
        self._logger.debug("move_pointer_completed", screen_id=screen_id, x=x, y=y)

    async def click_pointer(self, button: MouseButton, count: int, event_tag: int) -> None:
        """Post mouse-button clicks at the current pointer position.

        Args:
            button: Which mouse button to click.
            count: Number of clicks (1 = single, 2 = double, 3 = triple).
            event_tag: Magic integer written to kCGEventSourceUserData
                on every posted event.

        Raises:
            Error: If called on a non-macOS host, count is invalid, or
                the click fails.
        """
        self._logger.debug("click_pointer_started", button=button.value, count=count)
        self._ensure_macos_host()
        if count < 1:
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Click count must be >= 1, got {count}")

        for click_index in range(1, count + 1):
            if click_index > 1:
                await asyncio.sleep(_CLICK_INTER_CLICK_DELAY_SECONDS)
            await asyncio.to_thread(self._click_pointer_once, button, click_index, event_tag)

        self._logger.debug("click_pointer_completed", button=button.value, count=count)

    async def tap_key(self, key: Key, event_tag: int) -> None:
        """Press and release a single key, layout-aware for character keys.

        Args:
            key: Key identifier; must be in allowed_keys.
            event_tag: Magic integer written to kCGEventSourceUserData
                on every posted event.

        Raises:
            Error: If called on a non-macOS host, the key is not in
                allowed_keys, or the key cannot be produced on the
                current keyboard layout.
        """
        self._logger.debug("tap_key_started", key=key.value)
        self._ensure_macos_host()
        self._ensure_key_allowed(key=key)
        await asyncio.to_thread(self._tap_key, key, event_tag)
        self._logger.debug("tap_key_completed", key=key.value)

    async def press_keys_together(self, keys: list[Key], event_tag: int) -> None:
        """Press all keys down then release them in reverse order.

        Args:
            keys: Ordered list of keys; first listed is pressed first
                and released last.
            event_tag: Magic integer written to kCGEventSourceUserData
                on every posted event.

        Raises:
            Error: If called on a non-macOS host, any key is not in
                allowed_keys, or the key cannot be produced on the
                current keyboard layout.
        """
        self._logger.debug("press_keys_together_started", keys=[key.value for key in keys])
        self._ensure_macos_host()
        for key in keys:
            self._ensure_key_allowed(key=key)
        await asyncio.to_thread(self._press_keys_together, keys, event_tag)
        self._logger.debug("press_keys_together_completed", keys=[key.value for key in keys])

    async def type_text(self, text: str, event_tag: int) -> None:
        """Type a literal Unicode string, layout-independent.

        Args:
            text: Text to type.
            event_tag: Magic integer written to kCGEventSourceUserData
                on every posted event.

        Raises:
            Error: If called on a non-macOS host.
        """
        self._logger.debug("type_text_started", text_length=len(text))
        self._ensure_macos_host()
        for index, character in enumerate(text):
            if index > 0:
                await asyncio.sleep(_TYPE_TEXT_INTER_CHARACTER_DELAY_SECONDS)
            await asyncio.to_thread(self._post_unicode_event, character, event_tag)
        self._logger.debug("type_text_completed", text_length=len(text))

    def _ensure_macos_host(self) -> None:
        if sys.platform != "darwin":
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"MacosSystemAccess called on non-macOS host: {sys.platform}",
            )

    def _ensure_key_allowed(self, key: Key) -> None:
        """Raise NOT_SUPPORTED if the key is not available on macOS.

        Args:
            key: Key identifier to validate.

        Raises:
            Error: If the key is not in the macOS allowed set.
        """
        if key not in _ALLOWED_KEYS:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"Key {key.value} is not available on macOS",
            )

    def _list_screens(self) -> list[Screen]:
        display_ids = (c_uint32 * _MAX_DISPLAYS)()
        actual_count = c_uint32(0)

        status = _application_services.CGGetActiveDisplayList(
            _MAX_DISPLAYS, display_ids, byref(actual_count)
        )
        if status != 0:
            raise Error(
                ErrorCode.INTERNAL,
                f"CGGetActiveDisplayList failed with status {status}",
            )

        main_display_id = _application_services.CGMainDisplayID()

        screens: list[Screen] = []
        for index in range(actual_count.value):
            display_id = display_ids[index]
            screens.append(Screen(id=index + 1, is_primary=(display_id == main_display_id)))
        return screens

    def _capture_screen(self, screen_id: int) -> ScreenCapture:
        display_id = self._resolve_display_id(screen_id=screen_id)
        bounds = _application_services.CGDisplayBounds(display_id)

        image_ref = _application_services.CGWindowListCreateImage(
            bounds, _WINDOW_LIST_OPTION_ON_SCREEN_ONLY, _NULL_WINDOW_ID, _WINDOW_IMAGE_DEFAULT
        )
        if not image_ref:
            raise Error(
                ErrorCode.INTERNAL,
                f"CGWindowListCreateImage returned NULL for display {display_id}",
            )

        try:
            width = int(_application_services.CGImageGetWidth(image_ref))
            height = int(_application_services.CGImageGetHeight(image_ref))
            bytes_per_row = int(_application_services.CGImageGetBytesPerRow(image_ref))

            data_provider = _application_services.CGImageGetDataProvider(image_ref)
            if not data_provider:
                raise Error(ErrorCode.INTERNAL, "CGImageGetDataProvider returned NULL")

            data_ref = _application_services.CGDataProviderCopyData(data_provider)
            if not data_ref:
                raise Error(ErrorCode.INTERNAL, "CGDataProviderCopyData returned NULL")

            try:
                length = _core_foundation.CFDataGetLength(data_ref)
                byte_pointer = _core_foundation.CFDataGetBytePtr(data_ref)
                raw_bgra = ctypes.string_at(byte_pointer, length)
            finally:
                _core_foundation.CFRelease(data_ref)

            packed_bgra = self._strip_row_padding(
                raw_bgra=raw_bgra,
                width=width,
                height=height,
                bytes_per_row=bytes_per_row,
            )
            return ScreenCapture(bgra=packed_bgra, width=width, height=height)
        finally:
            _core_foundation.CFRelease(image_ref)

    def _strip_row_padding(
        self, raw_bgra: bytes, width: int, height: int, bytes_per_row: int
    ) -> bytes:
        """Remove per-row alignment padding so consumers see a packed buffer.

        Args:
            raw_bgra: Raw bytes returned by CoreGraphics, possibly padded
                so each row is exactly bytes_per_row bytes.
            width: Image width in pixels.
            height: Image height in pixels.
            bytes_per_row: Actual stride in bytes (always >= width * 4).

        Returns:
            BGRA buffer with stride == width * 4.
        """
        packed_bytes_per_row = width * 4
        if bytes_per_row == packed_bytes_per_row:
            return raw_bgra

        packed = bytearray(packed_bytes_per_row * height)
        for row in range(height):
            source_start = row * bytes_per_row
            destination_start = row * packed_bytes_per_row
            packed[destination_start : destination_start + packed_bytes_per_row] = raw_bgra[
                source_start : source_start + packed_bytes_per_row
            ]
        return bytes(packed)

    def _resolve_display_id(self, screen_id: int) -> int:
        display_ids = (c_uint32 * _MAX_DISPLAYS)()
        actual_count = c_uint32(0)

        status = _application_services.CGGetActiveDisplayList(
            _MAX_DISPLAYS, display_ids, byref(actual_count)
        )
        if status != 0:
            raise Error(
                ErrorCode.INTERNAL,
                f"CGGetActiveDisplayList failed with status {status}",
            )

        if screen_id < 1 or screen_id > actual_count.value:
            raise Error(
                ErrorCode.INVALID_ARGUMENT,
                f"Screen id {screen_id} is out of range (1..{actual_count.value})",
            )
        return int(display_ids[screen_id - 1])

    def _get_pointer_position(self, screen_id: int) -> PointerPosition | None:
        display_id = self._resolve_display_id(screen_id=screen_id)
        bounds = _application_services.CGDisplayBounds(display_id)

        event = _application_services.CGEventCreate(None)
        if not event:
            raise Error(ErrorCode.INTERNAL, "CGEventCreate returned NULL")

        try:
            cursor_point = _application_services.CGEventGetLocation(event)
        finally:
            _core_foundation.CFRelease(event)

        local_x_points = cursor_point.x - bounds.origin_x
        local_y_points = cursor_point.y - bounds.origin_y

        if (
            local_x_points < 0
            or local_y_points < 0
            or local_x_points >= bounds.width
            or local_y_points >= bounds.height
        ):
            return None

        rendered_pixel_width = self._get_rendered_pixel_width(display_id=display_id)
        scale = rendered_pixel_width / bounds.width if bounds.width > 0 else 1.0

        return PointerPosition(
            x=int(local_x_points * scale),
            y=int(local_y_points * scale),
        )

    def _get_rendered_pixel_width(self, display_id: int) -> int:
        """Get the pixel width of the display's current rendered mode.

        On Retina with default scaling this matches the native physical
        pixel count. In scaled modes ("Looks like 1680×1050") it returns
        the intermediate render width (e.g. 3360) — which is the actual
        width of CGWindowListCreateImage's output, the canonical pixel
        space for screen captures.

        Args:
            display_id: CGDirectDisplayID for the target display.

        Returns:
            Width in rendered pixels.

        Raises:
            Error: If the current display mode cannot be queried.
        """
        mode = _application_services.CGDisplayCopyDisplayMode(c_uint32(display_id))
        if not mode:
            raise Error(
                ErrorCode.INTERNAL,
                f"CGDisplayCopyDisplayMode returned NULL for display {display_id}",
            )
        try:
            return int(_application_services.CGDisplayModeGetPixelWidth(mode))
        finally:
            _application_services.CGDisplayModeRelease(mode)

    def _compute_target_point_in_global_space(self, screen_id: int, x: int, y: int) -> _CGPoint:
        """Convert screen-local pixel coords to a global point CGPoint.

        Args:
            screen_id: 1-based identifier returned by list_screens.
            x: Target x in screen-local pixels (top-left origin).
            y: Target y in screen-local pixels (top-left origin).

        Returns:
            CGPoint in global display point coordinates, ready for
            CGWarpMouseCursorPosition. Coordinates are clamped to the
            target screen's visible bounds.
        """
        display_id = self._resolve_display_id(screen_id=screen_id)
        bounds = _application_services.CGDisplayBounds(display_id)
        rendered_pixel_width = self._get_rendered_pixel_width(display_id=display_id)
        scale = rendered_pixel_width / bounds.width if bounds.width > 0 else 1.0

        local_x_points = x / scale if scale > 0 else 0.0
        local_y_points = y / scale if scale > 0 else 0.0

        global_x_points = bounds.origin_x + local_x_points
        global_y_points = bounds.origin_y + local_y_points

        clamped_x = max(bounds.origin_x, min(global_x_points, bounds.origin_x + bounds.width - 1))
        clamped_y = max(bounds.origin_y, min(global_y_points, bounds.origin_y + bounds.height - 1))

        return _CGPoint(x=clamped_x, y=clamped_y)

    async def _smooth_move_pointer(self, target_point: _CGPoint) -> None:
        """Animate the cursor from its current position to target_point.

        Uses an ease-in-out interpolation over roughly
        _MOVE_POINTER_TOTAL_DURATION_SECONDS. Sleeps between steps with
        asyncio.sleep so other conversations keep processing.

        Args:
            target_point: Destination in global display point coordinates.
        """
        start_point = await asyncio.to_thread(self._read_cursor_point)

        delta_x = target_point.x - start_point.x
        delta_y = target_point.y - start_point.y
        distance_points = (delta_x * delta_x + delta_y * delta_y) ** 0.5

        if distance_points < _MOVE_POINTER_JUMP_DISTANCE_POINTS:
            await asyncio.to_thread(self._warp_pointer_to, target_point)
            return

        step_count = int(
            max(
                _MOVE_POINTER_MIN_STEPS,
                min(_MOVE_POINTER_MAX_STEPS, distance_points / _MOVE_POINTER_PIXELS_PER_STEP),
            )
        )
        delay_per_step_seconds = _MOVE_POINTER_TOTAL_DURATION_SECONDS / step_count

        for step in range(1, step_count + 1):
            progress = step / step_count
            eased = self._ease_in_out_quad(progress)
            point = _CGPoint(
                x=start_point.x + delta_x * eased,
                y=start_point.y + delta_y * eased,
            )
            await asyncio.to_thread(self._warp_pointer_to, point)
            if step < step_count:
                await asyncio.sleep(delay_per_step_seconds)

        await asyncio.to_thread(self._warp_pointer_to, target_point)

    def _read_cursor_point(self) -> _CGPoint:
        event = _application_services.CGEventCreate(None)
        if not event:
            raise Error(ErrorCode.INTERNAL, "CGEventCreate returned NULL")
        try:
            point: _CGPoint = _application_services.CGEventGetLocation(event)
            return point
        finally:
            _core_foundation.CFRelease(event)

    def _warp_pointer_to(self, point: _CGPoint) -> None:
        status = _application_services.CGWarpMouseCursorPosition(point)
        if status != 0:
            raise Error(
                ErrorCode.INTERNAL, f"CGWarpMouseCursorPosition failed with status {status}"
            )
        _application_services.CGAssociateMouseAndMouseCursorPosition(c_bool(True))

    def _ease_in_out_quad(self, progress: float) -> float:
        if progress < 0.5:
            return 2 * progress * progress
        shifted = progress - 1
        return 1 - 2 * shifted * shifted

    def _click_pointer_once(self, button: MouseButton, click_state: int, event_tag: int) -> None:
        cursor_event = _application_services.CGEventCreate(None)
        if not cursor_event:
            raise Error(ErrorCode.INTERNAL, "CGEventCreate returned NULL")
        try:
            cursor_point = _application_services.CGEventGetLocation(cursor_event)
        finally:
            _core_foundation.CFRelease(cursor_event)

        if button == MouseButton.LEFT:
            down_type = _CG_EVENT_LEFT_MOUSE_DOWN
            up_type = _CG_EVENT_LEFT_MOUSE_UP
            cg_button = _CG_MOUSE_BUTTON_LEFT
        elif button == MouseButton.RIGHT:
            down_type = _CG_EVENT_RIGHT_MOUSE_DOWN
            up_type = _CG_EVENT_RIGHT_MOUSE_UP
            cg_button = _CG_MOUSE_BUTTON_RIGHT
        else:
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported mouse button: {button.value}")

        self._post_mouse_event(
            event_type=down_type,
            point=cursor_point,
            button=cg_button,
            click_state=click_state,
            event_tag=event_tag,
        )
        self._post_mouse_event(
            event_type=up_type,
            point=cursor_point,
            button=cg_button,
            click_state=click_state,
            event_tag=event_tag,
        )

    def _post_mouse_event(
        self, event_type: int, point: _CGPoint, button: int, click_state: int, event_tag: int
    ) -> None:
        event = _application_services.CGEventCreateMouseEvent(
            None, c_uint32(event_type), point, c_uint32(button)
        )
        if not event:
            raise Error(ErrorCode.INTERNAL, "CGEventCreateMouseEvent returned NULL")

        try:
            _application_services.CGEventSetIntegerValueField(
                event, c_uint32(_CG_EVENT_MOUSE_FIELD_CLICK_STATE), c_int64(click_state)
            )
            _application_services.CGEventSetIntegerValueField(
                event, c_uint32(_CG_EVENT_FIELD_SOURCE_USER_DATA), c_int64(event_tag)
            )
            _application_services.CGEventPost(_CG_HID_EVENT_TAP, event)
        finally:
            _core_foundation.CFRelease(event)

    def _tap_key(self, key: Key, event_tag: int) -> None:
        key_code = self._resolve_key_code(key=key)
        self._post_key_event(key_code=key_code, is_down=True, flags=0, event_tag=event_tag)
        self._post_key_event(key_code=key_code, is_down=False, flags=0, event_tag=event_tag)

    def _press_keys_together(self, keys: list[Key], event_tag: int) -> None:
        modifier_keys = [key for key in keys if key in _MODIFIER_FLAG_MASKS]
        regular_keys = [key for key in keys if key not in _MODIFIER_FLAG_MASKS]

        combined_flags = 0
        for modifier in modifier_keys:
            combined_flags |= _MODIFIER_FLAG_MASKS[modifier]

        modifier_codes = [self._resolve_key_code(key=key) for key in modifier_keys]
        regular_codes = [self._resolve_key_code(key=key) for key in regular_keys]

        for key_code in modifier_codes:
            self._post_key_event(key_code=key_code, is_down=True, flags=0, event_tag=event_tag)

        for key_code in regular_codes:
            self._post_key_event(
                key_code=key_code, is_down=True, flags=combined_flags, event_tag=event_tag
            )
            self._post_key_event(
                key_code=key_code, is_down=False, flags=combined_flags, event_tag=event_tag
            )

        for key_code in reversed(modifier_codes):
            self._post_key_event(key_code=key_code, is_down=False, flags=0, event_tag=event_tag)

    def _resolve_key_code(self, key: Key) -> int:
        if key in _NON_CHARACTER_KEY_CODES:
            return _NON_CHARACTER_KEY_CODES[key]
        if key in _CHARACTER_KEY_TO_CHAR:
            return self._translate_character_key(key=key)
        raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported key: {key.value}")

    def _translate_character_key(self, key: Key) -> int:
        target_character = _CHARACTER_KEY_TO_CHAR[key]
        keyboard_type = c_uint32(_carbon.LMGetKbdType())

        input_source = _carbon.TISCopyCurrentKeyboardLayoutInputSource()
        if not input_source:
            raise Error(
                ErrorCode.INTERNAL,
                "TISCopyCurrentKeyboardLayoutInputSource returned NULL",
            )

        try:
            layout_byte_pointer = self._read_layout_byte_pointer(input_source=input_source)

            for candidate_code in range(0, 128):
                produced = self._key_produces_character(
                    layout_byte_pointer=layout_byte_pointer,
                    key_code=candidate_code,
                    keyboard_type=keyboard_type,
                )
                if produced == target_character:
                    return candidate_code
        finally:
            _core_foundation.CFRelease(input_source)

        raise Error(
            ErrorCode.NOT_SUPPORTED,
            f"Key '{target_character}' is not directly produceable on the current keyboard layout",
        )

    def _read_layout_byte_pointer(self, input_source: c_void_p) -> c_void_p:
        """Resolve the input source's UnicodeKeyLayoutData byte pointer.

        Args:
            input_source: TIS input source owning the layout data.

        Returns:
            Byte pointer to the layout's CFData payload. Valid only while
            input_source is still retained by the caller.

        Raises:
            Error: If property creation, lookup or byte-pointer access fails.
        """
        property_name = _core_foundation.CFStringCreateWithCString(
            None,
            _TIS_KEYBOARD_LAYOUT_DATA_PROPERTY.encode("utf-8"),
            _CF_STRING_ENCODING_UTF8,
        )
        if not property_name:
            raise Error(
                ErrorCode.INTERNAL,
                f"CFStringCreateWithCString failed for: {_TIS_KEYBOARD_LAYOUT_DATA_PROPERTY}",
            )
        try:
            layout_data = _carbon.TISGetInputSourceProperty(input_source, property_name)
        finally:
            _core_foundation.CFRelease(property_name)

        if not layout_data:
            raise Error(
                ErrorCode.INTERNAL,
                "TISGetInputSourceProperty returned NULL",
            )

        byte_pointer = _core_foundation.CFDataGetBytePtr(c_void_p(layout_data))
        if not byte_pointer:
            raise Error(
                ErrorCode.INTERNAL,
                "CFDataGetBytePtr returned NULL for keyboard layout data",
            )
        return c_void_p(byte_pointer)

    def _key_produces_character(
        self, layout_byte_pointer: c_void_p, key_code: int, keyboard_type: c_uint32
    ) -> str | None:
        dead_key_state = c_uint32(0)
        unicode_buffer = (c_uint16 * _MAX_TYPED_CHARS)()
        actual_length = c_uint64(0)

        status = _carbon.UCKeyTranslate(
            layout_byte_pointer,
            c_uint16(key_code),
            c_uint16(_UC_KEY_ACTION_DOWN),
            c_uint32(0),
            keyboard_type,
            c_uint32(_UC_KEY_TRANSLATE_NO_DEAD_KEYS_MASK),
            byref(dead_key_state),
            c_uint64(_MAX_TYPED_CHARS),
            byref(actual_length),
            unicode_buffer,
        )
        if status != 0 or actual_length.value == 0:
            return None

        return "".join(chr(unicode_buffer[index]) for index in range(actual_length.value))

    def _post_key_event(self, key_code: int, is_down: bool, flags: int, event_tag: int) -> None:
        event = _application_services.CGEventCreateKeyboardEvent(
            None, c_uint16(key_code), c_bool(is_down)
        )
        if not event:
            raise Error(ErrorCode.INTERNAL, "CGEventCreateKeyboardEvent returned NULL")

        try:
            if flags != 0:
                _application_services.CGEventSetFlags(event, c_uint64(flags))
            _application_services.CGEventSetIntegerValueField(
                event, c_uint32(_CG_EVENT_FIELD_SOURCE_USER_DATA), c_int64(event_tag)
            )
            _application_services.CGEventPost(_CG_HID_EVENT_TAP, event)
        finally:
            _core_foundation.CFRelease(event)

    def _post_unicode_event(self, character: str, event_tag: int) -> None:
        utf16_units = character.encode("utf-16-le")
        unit_count = len(utf16_units) // 2
        unit_buffer = (c_uint16 * unit_count)(
            *(int.from_bytes(utf16_units[i * 2 : i * 2 + 2], "little") for i in range(unit_count))
        )

        down_event = _application_services.CGEventCreateKeyboardEvent(
            None, c_uint16(0), c_bool(True)
        )
        up_event = _application_services.CGEventCreateKeyboardEvent(
            None, c_uint16(0), c_bool(False)
        )
        if not down_event or not up_event:
            if down_event:
                _core_foundation.CFRelease(down_event)
            if up_event:
                _core_foundation.CFRelease(up_event)
            raise Error(ErrorCode.INTERNAL, "CGEventCreateKeyboardEvent returned NULL")

        try:
            _application_services.CGEventKeyboardSetUnicodeString(
                down_event, c_uint64(unit_count), unit_buffer
            )
            _application_services.CGEventKeyboardSetUnicodeString(
                up_event, c_uint64(unit_count), unit_buffer
            )
            _application_services.CGEventSetIntegerValueField(
                down_event, c_uint32(_CG_EVENT_FIELD_SOURCE_USER_DATA), c_int64(event_tag)
            )
            _application_services.CGEventSetIntegerValueField(
                up_event, c_uint32(_CG_EVENT_FIELD_SOURCE_USER_DATA), c_int64(event_tag)
            )
            _application_services.CGEventPost(_CG_HID_EVENT_TAP, down_event)
            _application_services.CGEventPost(_CG_HID_EVENT_TAP, up_event)
        finally:
            _core_foundation.CFRelease(down_event)
            _core_foundation.CFRelease(up_event)
