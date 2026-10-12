"""Windows implementation of SystemAccess using ctypes (user32 + gdi32).

All Win32 API calls live in this module. The real WindowsSystemAccess
class is defined inside the `sys.platform == "win32"` guard so the
ctypes Win32-only attributes are never accessed on other platforms.
On non-Windows hosts a stub class with the same public interface is
exposed; every method raises NOT_SUPPORTED so callers fail loudly.
"""

import asyncio
import ctypes
import sys
from ctypes import (
    POINTER,
    Structure,
    Union,
    byref,
    c_int,
    c_short,
    c_void_p,
    sizeof,
)
from ctypes.wintypes import (
    BOOL,
    DWORD,
    HDC,
    HMONITOR,
    HWND,
    LONG,
    LPARAM,
    LPRECT,
    POINT,
    RECT,
    UINT,
    WCHAR,
    WORD,
)

from .....common import Logger
from .....models import Error, ErrorCode
from ..base_system_access import BaseSystemAccess
from ..models import Key, MouseButton, PointerPosition, Screen, ScreenCapture

_INPUT_KEYBOARD = 1
_INPUT_MOUSE = 0
_KEYEVENTF_KEY_UP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_MOUSEEVENTF_LEFT_DOWN = 0x0002
_MOUSEEVENTF_LEFT_UP = 0x0004
_MOUSEEVENTF_RIGHT_DOWN = 0x0008
_MOUSEEVENTF_RIGHT_UP = 0x0010
_MONITORINFOF_PRIMARY = 0x00000001
_BI_RGB = 0
_DIB_RGB_COLORS = 0
_SRCCOPY = 0x00CC0020
_VK_SHIFT = 0x10
_VK_CONTROL = 0x11
_VK_MENU = 0x12
_VK_LWIN = 0x5B

_TYPE_TEXT_INTER_CHARACTER_DELAY_SECONDS = 0.002
_CLICK_INTER_CLICK_DELAY_SECONDS = 0.015

_MOVE_POINTER_TOTAL_DURATION_SECONDS = 0.5
_MOVE_POINTER_MIN_STEPS = 20
_MOVE_POINTER_MAX_STEPS = 60
_MOVE_POINTER_PIXELS_PER_STEP = 8
_MOVE_POINTER_JUMP_DISTANCE_PIXELS = 5


_NON_CHARACTER_KEY_CODES: dict[Key, int] = {
    Key.CONTROL: _VK_CONTROL,
    Key.SHIFT: _VK_SHIFT,
    Key.ALT: _VK_MENU,
    Key.WIN: _VK_LWIN,
    Key.HOME: 0x24,
    Key.END: 0x23,
    Key.PAGE_UP: 0x21,
    Key.PAGE_DOWN: 0x22,
    Key.ARROW_UP: 0x26,
    Key.ARROW_DOWN: 0x28,
    Key.ARROW_LEFT: 0x25,
    Key.ARROW_RIGHT: 0x27,
    Key.F1: 0x70,
    Key.F2: 0x71,
    Key.F3: 0x72,
    Key.F4: 0x73,
    Key.F5: 0x74,
    Key.F6: 0x75,
    Key.F7: 0x76,
    Key.F8: 0x77,
    Key.F9: 0x78,
    Key.F10: 0x79,
    Key.F11: 0x7A,
    Key.F12: 0x7B,
    Key.SPACE: 0x20,
    Key.TAB: 0x09,
    Key.ENTER: 0x0D,
    Key.BACKSPACE: 0x08,
    Key.DELETE: 0x2E,
    Key.ESCAPE: 0x1B,
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


if sys.platform == "win32":

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    class _MONITORINFOEX(Structure):
        _fields_ = [
            ("cbSize", DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", DWORD),
            ("szDevice", WCHAR * 32),
        ]

    class _BITMAPINFOHEADER(Structure):
        _fields_ = [
            ("biSize", DWORD),
            ("biWidth", LONG),
            ("biHeight", LONG),
            ("biPlanes", WORD),
            ("biBitCount", WORD),
            ("biCompression", DWORD),
            ("biSizeImage", DWORD),
            ("biXPelsPerMeter", LONG),
            ("biYPelsPerMeter", LONG),
            ("biClrUsed", DWORD),
            ("biClrImportant", DWORD),
        ]

    class _BITMAPINFO(Structure):
        _fields_ = [
            ("bmiHeader", _BITMAPINFOHEADER),
            ("bmiColors", DWORD * 3),
        ]

    class _KEYBDINPUT(Structure):
        _fields_ = [
            ("wVk", WORD),
            ("wScan", WORD),
            ("dwFlags", DWORD),
            ("time", DWORD),
            ("dwExtraInfo", c_void_p),
        ]

    class _MOUSEINPUT(Structure):
        _fields_ = [
            ("dx", LONG),
            ("dy", LONG),
            ("mouseData", DWORD),
            ("dwFlags", DWORD),
            ("time", DWORD),
            ("dwExtraInfo", c_void_p),
        ]

    class _HARDWAREINPUT(Structure):
        _fields_ = [
            ("uMsg", DWORD),
            ("wParamL", WORD),
            ("wParamH", WORD),
        ]

    class _INPUTUNION(Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(Structure):
        _fields_ = [("type", DWORD), ("u", _INPUTUNION)]

    _MONITOR_ENUM_PROC = ctypes.WINFUNCTYPE(BOOL, HMONITOR, HDC, LPRECT, LPARAM)

    _user32.EnumDisplayMonitors.argtypes = [HDC, LPRECT, _MONITOR_ENUM_PROC, LPARAM]
    _user32.EnumDisplayMonitors.restype = BOOL
    _user32.GetMonitorInfoW.argtypes = [HMONITOR, POINTER(_MONITORINFOEX)]
    _user32.GetMonitorInfoW.restype = BOOL
    _user32.GetDC.argtypes = [HWND]
    _user32.GetDC.restype = HDC
    _user32.ReleaseDC.argtypes = [HWND, HDC]
    _user32.ReleaseDC.restype = c_int
    _gdi32.CreateCompatibleDC.argtypes = [HDC]
    _gdi32.CreateCompatibleDC.restype = HDC
    _gdi32.CreateCompatibleBitmap.argtypes = [HDC, c_int, c_int]
    _gdi32.CreateCompatibleBitmap.restype = c_void_p
    _gdi32.SelectObject.argtypes = [HDC, c_void_p]
    _gdi32.SelectObject.restype = c_void_p
    _gdi32.BitBlt.argtypes = [HDC, c_int, c_int, c_int, c_int, HDC, c_int, c_int, DWORD]
    _gdi32.BitBlt.restype = BOOL
    _gdi32.GetDIBits.argtypes = [HDC, c_void_p, UINT, UINT, c_void_p, POINTER(_BITMAPINFO), UINT]
    _gdi32.GetDIBits.restype = c_int
    _gdi32.DeleteObject.argtypes = [c_void_p]
    _gdi32.DeleteObject.restype = BOOL
    _gdi32.DeleteDC.argtypes = [HDC]
    _gdi32.DeleteDC.restype = BOOL
    _user32.SendInput.argtypes = [UINT, POINTER(_INPUT), c_int]
    _user32.SendInput.restype = UINT
    _user32.GetKeyboardLayout.argtypes = [DWORD]
    _user32.GetKeyboardLayout.restype = c_void_p
    _user32.GetCursorPos.argtypes = [POINTER(POINT)]
    _user32.GetCursorPos.restype = BOOL
    _user32.SetCursorPos.argtypes = [c_int, c_int]
    _user32.SetCursorPos.restype = BOOL
    _user32.VkKeyScanExW.argtypes = [WCHAR, c_void_p]
    _user32.VkKeyScanExW.restype = c_short

    _user32.SetProcessDpiAwarenessContext.argtypes = [c_void_p]
    _user32.SetProcessDpiAwarenessContext.restype = BOOL

    # Per-Monitor DPI Aware v2 context handle (HANDLE-typed sentinel).
    # Without this, Windows reports logical (scaled) screen coordinates;
    # GetMonitorInfo returns the scaled rect and BitBlt copies only that
    # many physical pixels — producing a top-left crop of the real screen
    # whenever the user's display scaling is above 100%.
    _DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

    # Called once at module import. The Windows DPI awareness mode is a
    # process-global lock: SetProcessDpiAwarenessContext fails on the
    # second call (ERROR_ACCESS_DENIED). Python caches module objects
    # in sys.modules, so this line never executes twice in the same
    # process — even if WindowsSystemAccess is instantiated repeatedly
    # by brick refresh cycles.
    _user32.SetProcessDpiAwarenessContext(c_void_p(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))

    class WindowsSystemAccess(BaseSystemAccess):
        """Windows implementation of SystemAccess using user32 and gdi32."""

        def __init__(self) -> None:
            """Initialize Windows system access."""
            self._logger = Logger.get_logger(
                "bricks.ui.system_access.implementations.windows_system_access"
            )

        @property
        def allowed_keys(self) -> set[Key]:
            """Get the set of keys supported on Windows.

            Returns:
                All Key members the Windows implementation can produce.
            """
            return _ALLOWED_KEYS

        async def list_screens(self) -> list[Screen]:
            """Enumerate connected displays via EnumDisplayMonitors.

            Returns:
                List of Screen entries; id is 1-based.

            Raises:
                Error: If enumeration fails.
            """
            self._logger.debug("list_screens_started")
            screens = await asyncio.to_thread(self._list_screens)
            self._logger.debug("list_screens_completed", count=len(screens))
            return screens

        async def capture_screen(self, screen_id: int) -> ScreenCapture:
            """Capture one display as raw BGRA via BitBlt.

            Args:
                screen_id: 1-based identifier returned by list_screens.

            Returns:
                ScreenCapture with raw BGRA bytes, width and height.

            Raises:
                Error: If the screen id is out of range or capture fails.
            """
            self._logger.debug("capture_screen_started", screen_id=screen_id)
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
            """Resolve the pointer position via GetCursorPos.

            Args:
                screen_id: 1-based identifier returned by list_screens.

            Returns:
                PointerPosition in screen-local pixels if the pointer is
                on this screen, None otherwise.

            Raises:
                Error: If the screen id is out of range or the query fails.
            """
            self._logger.debug("get_pointer_position_started", screen_id=screen_id)
            position = await asyncio.to_thread(self._get_pointer_position, screen_id)
            self._logger.debug(
                "get_pointer_position_completed",
                screen_id=screen_id,
                x=position.x if position else None,
                y=position.y if position else None,
                on_screen=position is not None,
            )
            return position

        async def click_pointer(self, button: MouseButton, count: int, event_tag: int) -> None:
            """Post mouse-button clicks at the current pointer position.

            Args:
                button: Which mouse button to click.
                count: Number of clicks (1 = single, 2 = double, 3 = triple).
                event_tag: Magic integer written to dwExtraInfo on every
                    SendInput event.

            Raises:
                Error: If count is invalid or the click fails.
            """
            self._logger.debug("click_pointer_started", button=button.value, count=count)
            if count < 1:
                raise Error(ErrorCode.INVALID_ARGUMENT, f"Click count must be >= 1, got {count}")

            for click_index in range(1, count + 1):
                if click_index > 1:
                    await asyncio.sleep(_CLICK_INTER_CLICK_DELAY_SECONDS)
                await asyncio.to_thread(self._click_pointer_once, button, event_tag)

            self._logger.debug("click_pointer_completed", button=button.value, count=count)

        async def move_pointer(self, screen_id: int, x: int, y: int) -> None:
            """Smoothly move the pointer to a screen-local pixel position.

            Args:
                screen_id: 1-based identifier returned by list_screens.
                x: Target x in screen-local pixels (top-left origin).
                y: Target y in screen-local pixels (top-left origin).

            Raises:
                Error: If the screen id is out of range or the move fails.
            """
            self._logger.debug("move_pointer_started", screen_id=screen_id, x=x, y=y)
            target_x, target_y = await asyncio.to_thread(
                self._compute_target_in_global_space, screen_id, x, y
            )
            await self._smooth_move_pointer(target_x=target_x, target_y=target_y)
            self._logger.debug("move_pointer_completed", screen_id=screen_id, x=x, y=y)

        async def tap_key(self, key: Key, event_tag: int) -> None:
            """Press and release a single key, layout-aware for character keys.

            Args:
                key: Key identifier; must be in allowed_keys.
                event_tag: Magic integer written to dwExtraInfo on every
                    SendInput event.

            Raises:
                Error: If the key is not in allowed_keys or cannot be
                    produced on the current keyboard layout.
            """
            self._logger.debug("tap_key_started", key=key.value)
            self._ensure_key_allowed(key=key)
            await asyncio.to_thread(self._tap_key, key, event_tag)
            self._logger.debug("tap_key_completed", key=key.value)

        async def press_keys_together(self, keys: list[Key], event_tag: int) -> None:
            """Press all keys down then release them in reverse order.

            Args:
                keys: Ordered list of keys.
                event_tag: Magic integer written to dwExtraInfo on every
                    SendInput event.

            Raises:
                Error: If any key is not in allowed_keys or cannot be
                    produced on the current keyboard layout.
            """
            self._logger.debug("press_keys_together_started", keys=[key.value for key in keys])
            for key in keys:
                self._ensure_key_allowed(key=key)
            await asyncio.to_thread(self._press_keys_together, keys, event_tag)
            self._logger.debug("press_keys_together_completed", keys=[key.value for key in keys])

        async def type_text(self, text: str, event_tag: int) -> None:
            """Type a literal Unicode string via KEYEVENTF_UNICODE.

            Args:
                text: Text to type.
                event_tag: Magic integer written to dwExtraInfo on every
                    SendInput event.
            """
            self._logger.debug("type_text_started", text_length=len(text))
            for index, character in enumerate(text):
                if index > 0:
                    await asyncio.sleep(_TYPE_TEXT_INTER_CHARACTER_DELAY_SECONDS)
                await asyncio.to_thread(self._post_unicode_character, character, event_tag)
            self._logger.debug("type_text_completed", text_length=len(text))

        def _ensure_key_allowed(self, key: Key) -> None:
            if key not in _ALLOWED_KEYS:
                raise Error(
                    ErrorCode.NOT_SUPPORTED,
                    f"Key {key.value} is not available on Windows",
                )

        def _list_screens(self) -> list[Screen]:
            screens: list[Screen] = []

            def callback(monitor: int, dc: int, rect: int, lparam: int) -> int:
                info = _MONITORINFOEX()
                info.cbSize = sizeof(_MONITORINFOEX)
                if _user32.GetMonitorInfoW(monitor, byref(info)):
                    is_primary = bool(info.dwFlags & _MONITORINFOF_PRIMARY)
                    screens.append(Screen(id=len(screens) + 1, is_primary=is_primary))
                return 1

            if not _user32.EnumDisplayMonitors(None, None, _MONITOR_ENUM_PROC(callback), 0):
                raise Error(ErrorCode.INTERNAL, "EnumDisplayMonitors failed")
            return screens

        def _capture_screen(self, screen_id: int) -> ScreenCapture:
            monitor_rect = self._resolve_monitor_rect(screen_id=screen_id)
            width = monitor_rect.right - monitor_rect.left
            height = monitor_rect.bottom - monitor_rect.top

            screen_dc = _user32.GetDC(None)
            if not screen_dc:
                raise Error(ErrorCode.INTERNAL, "GetDC returned NULL")

            memory_dc = _gdi32.CreateCompatibleDC(screen_dc)
            bitmap = _gdi32.CreateCompatibleBitmap(screen_dc, width, height)
            if not memory_dc or not bitmap:
                _user32.ReleaseDC(None, screen_dc)
                if memory_dc:
                    _gdi32.DeleteDC(memory_dc)
                if bitmap:
                    _gdi32.DeleteObject(bitmap)
                raise Error(ErrorCode.INTERNAL, "Failed to create compatible DC or bitmap")

            try:
                previous_bitmap = _gdi32.SelectObject(memory_dc, bitmap)
                try:
                    blit_ok = _gdi32.BitBlt(
                        memory_dc,
                        0,
                        0,
                        width,
                        height,
                        screen_dc,
                        monitor_rect.left,
                        monitor_rect.top,
                        _SRCCOPY,
                    )
                    if not blit_ok:
                        raise Error(ErrorCode.INTERNAL, "BitBlt failed")

                    bgra_bytes = self._extract_bgra_from_bitmap(
                        screen_dc=screen_dc, bitmap=bitmap, width=width, height=height
                    )
                finally:
                    _gdi32.SelectObject(memory_dc, previous_bitmap)
            finally:
                _gdi32.DeleteObject(bitmap)
                _gdi32.DeleteDC(memory_dc)
                _user32.ReleaseDC(None, screen_dc)

            return ScreenCapture(bgra=bgra_bytes, width=width, height=height)

        def _resolve_monitor_rect(self, screen_id: int) -> "RECT":
            rects: list[RECT] = []

            def callback(monitor: int, dc: int, rect: int, lparam: int) -> int:
                info = _MONITORINFOEX()
                info.cbSize = sizeof(_MONITORINFOEX)
                if _user32.GetMonitorInfoW(monitor, byref(info)):
                    rects.append(info.rcMonitor)
                return 1

            if not _user32.EnumDisplayMonitors(None, None, _MONITOR_ENUM_PROC(callback), 0):
                raise Error(ErrorCode.INTERNAL, "EnumDisplayMonitors failed")

            if screen_id < 1 or screen_id > len(rects):
                raise Error(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Screen id {screen_id} is out of range (1..{len(rects)})",
                )
            return rects[screen_id - 1]

        def _get_pointer_position(self, screen_id: int) -> PointerPosition | None:
            monitor_rect = self._resolve_monitor_rect(screen_id=screen_id)

            cursor_point = POINT()
            if not _user32.GetCursorPos(byref(cursor_point)):
                raise Error(ErrorCode.INTERNAL, "GetCursorPos failed")

            if (
                cursor_point.x < monitor_rect.left
                or cursor_point.y < monitor_rect.top
                or cursor_point.x >= monitor_rect.right
                or cursor_point.y >= monitor_rect.bottom
            ):
                return None

            return PointerPosition(
                x=cursor_point.x - monitor_rect.left,
                y=cursor_point.y - monitor_rect.top,
            )

        def _click_pointer_once(self, button: MouseButton, event_tag: int) -> None:
            if button == MouseButton.LEFT:
                down_flag = _MOUSEEVENTF_LEFT_DOWN
                up_flag = _MOUSEEVENTF_LEFT_UP
            elif button == MouseButton.RIGHT:
                down_flag = _MOUSEEVENTF_RIGHT_DOWN
                up_flag = _MOUSEEVENTF_RIGHT_UP
            else:
                raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported mouse button: {button.value}")

            input_array = (_INPUT * 2)()
            input_array[0] = _INPUT(
                type=_INPUT_MOUSE,
                u=_INPUTUNION(
                    mi=_MOUSEINPUT(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=down_flag,
                        time=0,
                        dwExtraInfo=c_void_p(event_tag),
                    )
                ),
            )
            input_array[1] = _INPUT(
                type=_INPUT_MOUSE,
                u=_INPUTUNION(
                    mi=_MOUSEINPUT(
                        dx=0,
                        dy=0,
                        mouseData=0,
                        dwFlags=up_flag,
                        time=0,
                        dwExtraInfo=c_void_p(event_tag),
                    )
                ),
            )

            sent = _user32.SendInput(2, input_array, sizeof(_INPUT))
            if sent != 2:
                raise Error(
                    ErrorCode.INTERNAL,
                    f"SendInput sent {sent} of 2 mouse events for {button.value} click",
                )

        def _compute_target_in_global_space(
            self, screen_id: int, x: int, y: int
        ) -> tuple[int, int]:
            monitor_rect = self._resolve_monitor_rect(screen_id=screen_id)
            global_x = monitor_rect.left + x
            global_y = monitor_rect.top + y

            clamped_x = max(monitor_rect.left, min(global_x, monitor_rect.right - 1))
            clamped_y = max(monitor_rect.top, min(global_y, monitor_rect.bottom - 1))
            return clamped_x, clamped_y

        async def _smooth_move_pointer(self, target_x: int, target_y: int) -> None:
            start_x, start_y = await asyncio.to_thread(self._read_cursor_point)

            delta_x = target_x - start_x
            delta_y = target_y - start_y
            distance_pixels = (delta_x * delta_x + delta_y * delta_y) ** 0.5

            if distance_pixels < _MOVE_POINTER_JUMP_DISTANCE_PIXELS:
                await asyncio.to_thread(self._warp_pointer_to, target_x, target_y)
                return

            step_count = int(
                max(
                    _MOVE_POINTER_MIN_STEPS,
                    min(_MOVE_POINTER_MAX_STEPS, distance_pixels / _MOVE_POINTER_PIXELS_PER_STEP),
                )
            )
            delay_per_step_seconds = _MOVE_POINTER_TOTAL_DURATION_SECONDS / step_count

            for step in range(1, step_count + 1):
                progress = step / step_count
                eased = self._ease_in_out_quad(progress)
                point_x = int(start_x + delta_x * eased)
                point_y = int(start_y + delta_y * eased)
                await asyncio.to_thread(self._warp_pointer_to, point_x, point_y)
                if step < step_count:
                    await asyncio.sleep(delay_per_step_seconds)

            await asyncio.to_thread(self._warp_pointer_to, target_x, target_y)

        def _read_cursor_point(self) -> tuple[int, int]:
            cursor_point = POINT()
            if not _user32.GetCursorPos(byref(cursor_point)):
                raise Error(ErrorCode.INTERNAL, "GetCursorPos failed")
            return cursor_point.x, cursor_point.y

        def _warp_pointer_to(self, x: int, y: int) -> None:
            if not _user32.SetCursorPos(x, y):
                raise Error(ErrorCode.INTERNAL, f"SetCursorPos failed at ({x}, {y})")

        def _ease_in_out_quad(self, progress: float) -> float:
            if progress < 0.5:
                return 2 * progress * progress
            shifted = progress - 1
            return 1 - 2 * shifted * shifted

        def _extract_bgra_from_bitmap(
            self, screen_dc: int, bitmap: int, width: int, height: int
        ) -> bytes:
            bitmap_info = _BITMAPINFO()
            bitmap_info.bmiHeader.biSize = sizeof(_BITMAPINFOHEADER)
            bitmap_info.bmiHeader.biWidth = width
            bitmap_info.bmiHeader.biHeight = -height
            bitmap_info.bmiHeader.biPlanes = 1
            bitmap_info.bmiHeader.biBitCount = 32
            bitmap_info.bmiHeader.biCompression = _BI_RGB

            buffer = ctypes.create_string_buffer(width * height * 4)
            rows_copied = _gdi32.GetDIBits(
                screen_dc, bitmap, 0, height, buffer, byref(bitmap_info), _DIB_RGB_COLORS
            )
            if rows_copied == 0:
                raise Error(ErrorCode.INTERNAL, "GetDIBits failed")

            return bytes(buffer.raw)

        def _tap_key(self, key: Key, event_tag: int) -> None:
            virtual_key, shift_state = self._resolve_virtual_key(key=key)
            needs_shift = bool(shift_state & 0x01)
            needs_ctrl = bool(shift_state & 0x02)
            needs_alt = bool(shift_state & 0x04)

            if needs_shift:
                self._post_key_event(virtual_key=_VK_SHIFT, is_down=True, event_tag=event_tag)
            if needs_ctrl:
                self._post_key_event(virtual_key=_VK_CONTROL, is_down=True, event_tag=event_tag)
            if needs_alt:
                self._post_key_event(virtual_key=_VK_MENU, is_down=True, event_tag=event_tag)

            self._post_key_event(virtual_key=virtual_key, is_down=True, event_tag=event_tag)
            self._post_key_event(virtual_key=virtual_key, is_down=False, event_tag=event_tag)

            if needs_alt:
                self._post_key_event(virtual_key=_VK_MENU, is_down=False, event_tag=event_tag)
            if needs_ctrl:
                self._post_key_event(virtual_key=_VK_CONTROL, is_down=False, event_tag=event_tag)
            if needs_shift:
                self._post_key_event(virtual_key=_VK_SHIFT, is_down=False, event_tag=event_tag)

        def _press_keys_together(self, keys: list[Key], event_tag: int) -> None:
            virtual_keys = [self._resolve_virtual_key(key=key)[0] for key in keys]

            event_count = len(virtual_keys) * 2
            input_array = (_INPUT * event_count)()

            for index, virtual_key in enumerate(virtual_keys):
                input_array[index] = _INPUT(
                    type=_INPUT_KEYBOARD,
                    u=_INPUTUNION(
                        ki=_KEYBDINPUT(
                            wVk=virtual_key,
                            wScan=0,
                            dwFlags=0,
                            time=0,
                            dwExtraInfo=c_void_p(event_tag),
                        )
                    ),
                )

            for index, virtual_key in enumerate(reversed(virtual_keys)):
                input_array[len(virtual_keys) + index] = _INPUT(
                    type=_INPUT_KEYBOARD,
                    u=_INPUTUNION(
                        ki=_KEYBDINPUT(
                            wVk=virtual_key,
                            wScan=0,
                            dwFlags=_KEYEVENTF_KEY_UP,
                            time=0,
                            dwExtraInfo=c_void_p(event_tag),
                        )
                    ),
                )

            sent = _user32.SendInput(event_count, input_array, sizeof(_INPUT))
            if sent != event_count:
                raise Error(
                    ErrorCode.INTERNAL,
                    f"SendInput sent {sent} of {event_count} events",
                )

        def _post_unicode_character(self, character: str, event_tag: int) -> None:
            utf16_bytes = character.encode("utf-16-le")
            for index in range(0, len(utf16_bytes), 2):
                code_unit = int.from_bytes(utf16_bytes[index : index + 2], "little")
                self._post_unicode_event(code_unit=code_unit, event_tag=event_tag)

        def _resolve_virtual_key(self, key: Key) -> tuple[int, int]:
            if key in _NON_CHARACTER_KEY_CODES:
                return _NON_CHARACTER_KEY_CODES[key], 0
            if key in _CHARACTER_KEY_TO_CHAR:
                return self._translate_character_key(key=key)
            raise Error(ErrorCode.NOT_SUPPORTED, f"Unsupported key: {key.value}")

        def _translate_character_key(self, key: Key) -> tuple[int, int]:
            character = _CHARACTER_KEY_TO_CHAR[key]
            layout = _user32.GetKeyboardLayout(0)
            result = _user32.VkKeyScanExW(character, layout)
            if result == -1:
                raise Error(
                    ErrorCode.NOT_SUPPORTED,
                    f"Key '{character}' is not directly produceable on the current keyboard layout",
                )

            virtual_key = result & 0xFF
            shift_state = (result >> 8) & 0xFF
            return virtual_key, shift_state

        def _post_key_event(self, virtual_key: int, is_down: bool, event_tag: int) -> None:
            flags = 0 if is_down else _KEYEVENTF_KEY_UP
            keyboard_input = _KEYBDINPUT(
                wVk=virtual_key,
                wScan=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=c_void_p(event_tag),
            )
            input_event = _INPUT(type=_INPUT_KEYBOARD, u=_INPUTUNION(ki=keyboard_input))
            sent = _user32.SendInput(1, byref(input_event), sizeof(_INPUT))
            if sent != 1:
                raise Error(ErrorCode.INTERNAL, f"SendInput failed for VK {virtual_key}")

        def _post_unicode_event(self, code_unit: int, event_tag: int) -> None:
            for flags in (_KEYEVENTF_UNICODE, _KEYEVENTF_UNICODE | _KEYEVENTF_KEY_UP):
                keyboard_input = _KEYBDINPUT(
                    wVk=0,
                    wScan=code_unit,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=c_void_p(event_tag),
                )
                input_event = _INPUT(type=_INPUT_KEYBOARD, u=_INPUTUNION(ki=keyboard_input))
                sent = _user32.SendInput(1, byref(input_event), sizeof(_INPUT))
                if sent != 1:
                    raise Error(ErrorCode.INTERNAL, "SendInput failed for unicode event")

else:

    class WindowsSystemAccess(BaseSystemAccess):
        """Stub for non-Windows hosts; every method raises NOT_SUPPORTED."""

        def __init__(self) -> None:
            """Initialize Windows system access stub."""
            self._logger = Logger.get_logger(
                "bricks.ui.system_access.implementations.windows_system_access"
            )

        @property
        def allowed_keys(self) -> set[Key]:
            return _ALLOWED_KEYS

        async def list_screens(self) -> list[Screen]:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def capture_screen(self, screen_id: int) -> ScreenCapture:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def get_pointer_position(self, screen_id: int) -> PointerPosition | None:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def click_pointer(self, button: MouseButton, count: int, event_tag: int) -> None:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def move_pointer(self, screen_id: int, x: int, y: int) -> None:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def tap_key(self, key: Key, event_tag: int) -> None:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def press_keys_together(self, keys: list[Key], event_tag: int) -> None:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )

        async def type_text(self, text: str, event_tag: int) -> None:
            raise Error(
                ErrorCode.NOT_SUPPORTED,
                f"WindowsSystemAccess called on non-Windows host: {sys.platform}",
            )
