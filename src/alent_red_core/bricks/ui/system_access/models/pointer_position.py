from dataclasses import dataclass


@dataclass(frozen=True)
class PointerPosition:
    """Pointer position in pixels within a captured screen.

    The coordinate space is top-left origin, matching how ScreenCapture
    bytes are laid out (row-major, first row = top). x and y are always
    >= 0 and within the screen's pixel dimensions.
    """

    x: int
    y: int
