from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    """A skill discovered on disk, identified by root label and name."""

    id: str
    name: str
    description: str
    directory: Path
    body: str
