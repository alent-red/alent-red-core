from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillRoot:
    """A directory whose immediate subdirectories are skills."""

    label: str
    path: Path
    writable: bool
    description: str
