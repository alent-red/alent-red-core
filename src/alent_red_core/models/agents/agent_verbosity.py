from enum import Enum


class AgentVerbosity(str, Enum):
    """Verbosity level for agent responses."""

    DEFAULT = "default"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
