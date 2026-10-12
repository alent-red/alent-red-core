from enum import Enum


class BrickConfigUIMovePointerGeometry(str, Enum):
    """Shape of the location the vision model reports for a described UI element."""

    POINT = "point"
    BOUNDING_BOX = "bounding_box"
