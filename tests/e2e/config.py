from pathlib import Path

import yaml
from pydantic import BaseModel


class TimeoutsConfig(BaseModel):
    """Timeouts used by the test infrastructure."""

    server_readiness_seconds: int


class AnthropicProviderConfig(BaseModel):
    """Anthropic provider configuration for tests."""

    api_key: str


class OpenAIProviderConfig(BaseModel):
    """OpenAI provider configuration for tests."""

    api_key: str


class ProvidersConfig(BaseModel):
    """All provider configurations available to tests."""

    anthropic: AnthropicProviderConfig
    openai: OpenAIProviderConfig


class TestConfig(BaseModel):
    """Top-level test configuration loaded from tests/config.yml."""

    providers: ProvidersConfig
    timeouts: TimeoutsConfig


def load_test_config() -> TestConfig:
    """Load and validate the test config from tests/config.yml.

    Returns:
        Parsed and validated TestConfig.

    Raises:
        ValidationError: If the YAML is malformed or missing required keys.
        FileNotFoundError: If tests/config.yml does not exist.
    """
    config_path = Path(__file__).parent.parent / "config.yml"
    with open(config_path, "r") as config_file:
        raw_config = yaml.safe_load(config_file)
    return TestConfig.model_validate(raw_config)
