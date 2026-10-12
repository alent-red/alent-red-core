from pydantic import BaseModel

from ..types import TrimmedNonEmptyStr


class Tool(BaseModel):
    """Tool definition for bricks."""

    name: TrimmedNonEmptyStr
    description: TrimmedNonEmptyStr
    parameters_schema: dict[str, object]
