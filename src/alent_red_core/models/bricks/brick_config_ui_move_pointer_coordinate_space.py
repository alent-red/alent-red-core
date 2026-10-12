from enum import Enum


class BrickConfigUIMovePointerCoordinateSpace(str, Enum):
    """Coordinate space the vision model reports locations in."""

    PIXELS = "pixels"
    NORMALIZED_1000 = "normalized_1000"
