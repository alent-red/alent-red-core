from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenCapture:
    """Raw screen capture as a packed BGRA pixel buffer.

    The pixel layout is canonical across operating systems: 4 bytes per
    pixel in BGRA order, row-major, no row padding (stride == width * 4).
    Consumers feed this to Pillow with
    `Image.frombytes("RGB", (width, height), bgra, "raw", "BGRX")`.
    """

    bgra: bytes
    width: int
    height: int
