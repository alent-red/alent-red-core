from typing import TYPE_CHECKING, Annotated, Union
from sqlmodel import Field, Relationship
from pydantic import Discriminator

from ..base import Base
from ..types import ModelJSON, TrimmedNonEmptyStr
from .provider_config_anthropic import ProviderConfigAnthropic
from .provider_config_openai import ProviderConfigOpenAI
from .provider_config_lm_studio import ProviderConfigLMStudio
from .provider_config_custom import ProviderConfigCustom

if TYPE_CHECKING:
    from ..llm_models import LlmModel

ProviderConfig = Annotated[
    Union[
        ProviderConfigAnthropic,
        ProviderConfigOpenAI,
        ProviderConfigLMStudio,
        ProviderConfigCustom,
    ],
    Discriminator("type"),
]


class Provider(Base, table=True):
    """Provider entity."""

    name: TrimmedNonEmptyStr = Field(unique=True)
    config: ProviderConfig = Field(sa_type=ModelJSON(ProviderConfig))

    llm_models: list["LlmModel"] = Relationship(
        back_populates="provider",
        sa_relationship_kwargs={"passive_deletes": True},
    )
