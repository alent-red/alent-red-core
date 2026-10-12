from enum import Enum


class BrickConfigType(str, Enum):
    """Brick configuration type enumeration."""

    UI = "ui"
    CODE = "code"
    SYSTEM = "system"
    SCHEDULER = "scheduler"
    RENDERER = "renderer"
    BROWSER = "browser"
    AGENT = "agent"
    CUSTOM = "custom"
    VISION = "vision"
    SKILLS = "skills"
