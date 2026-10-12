from typing import Union

from ..messages import MessageContent
from .llm_usage import LlmUsage

LlmStreamItem = Union[MessageContent, LlmUsage]
