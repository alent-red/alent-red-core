from enum import Enum


class AgentReasoning(str, Enum):
    """Reasoning depth for agent processing."""

    DEFAULT = "default"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
