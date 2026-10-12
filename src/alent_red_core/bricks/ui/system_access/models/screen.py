from dataclasses import dataclass


@dataclass(frozen=True)
class Screen:
    """Connected display as exposed by the host operating system."""

    id: int
    is_primary: bool
