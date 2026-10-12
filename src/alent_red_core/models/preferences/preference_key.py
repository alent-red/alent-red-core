from enum import Enum


class PreferenceKey(str, Enum):
    """Available preference keys."""

    # Prompt preferences
    SYSTEM_PROMPT = "system_prompt"
    AGENT_PROMPT_PLACEHOLDER = "agent_prompt_placeholder"
    BRICK_PROMPT_PLACEHOLDER = "brick_prompt_placeholder"
    BRICK_PROMPT_SEPARATOR = "brick_prompt_separator"
    BRICK_TOOL_NAME_SEPARATOR = "brick_tool_name_separator"
    ATTACHED_FILE_PATH_PROMPT_PREFIX = "attached_file_path_prompt_prefix"
    ATTACHED_FILE_PATH_PROMPT_SEPARATOR = "attached_file_path_prompt_separator"
    NO_TOOL_RESPONSE_PROMPT = "no_tool_response_prompt"

    # Provider base URLs
    OPEN_AI_BASE_URL = "open_ai_base_url"
    ANTHROPIC_BASE_URL = "anthropic_base_url"

    # LLM preferences
    LLM_STREAM = "llm_stream"

    # Anthropic API format preferences
    ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS = "anthropic_reasoning_minimal_budget_tokens"
    ANTHROPIC_REASONING_LOW_BUDGET_TOKENS = "anthropic_reasoning_low_budget_tokens"
    ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS = "anthropic_reasoning_medium_budget_tokens"
    ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS = "anthropic_reasoning_high_budget_tokens"
    ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS = "anthropic_reasoning_xhigh_budget_tokens"
    ANTHROPIC_CACHE_MEDIUM_TTL = "anthropic_cache_medium_ttl"
    ANTHROPIC_CACHE_HIGH_TTL = "anthropic_cache_high_ttl"
