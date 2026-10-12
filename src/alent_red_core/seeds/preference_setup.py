from ..database import Database
from ..models import (
    PreferenceInput,
    PreferenceKey,
    PreferenceValueBool,
    PreferenceValueInt,
    PreferenceValueString,
)


class PreferenceSetup:
    """Default preference seeds for first-run initialization."""

    @staticmethod
    async def run(database: Database) -> None:
        """Seed default preferences into the database, skipping existing ones.

        Args:
            database: Database instance to seed preferences into.
        """
        await database.preferences.save_many(PreferenceSetup._get_preferences(), skip_existing=True)

    @staticmethod
    def _get_preferences() -> list[PreferenceInput]:
        return [
            # Prompt preferences
            PreferenceInput(
                key=PreferenceKey.SYSTEM_PROMPT,
                value=PreferenceValueString(value=PreferenceSetup._get_system_prompt()),
            ),
            PreferenceInput(
                key=PreferenceKey.AGENT_PROMPT_PLACEHOLDER,
                value=PreferenceValueString(value="{{AGENT_PROMPT}}"),
            ),
            PreferenceInput(
                key=PreferenceKey.BRICK_PROMPT_PLACEHOLDER,
                value=PreferenceValueString(value="{{BRICK_PROMPT}}"),
            ),
            PreferenceInput(
                key=PreferenceKey.BRICK_PROMPT_SEPARATOR,
                value=PreferenceValueString(value="\n\n"),
            ),
            PreferenceInput(
                key=PreferenceKey.BRICK_TOOL_NAME_SEPARATOR,
                value=PreferenceValueString(value="__"),
            ),
            PreferenceInput(
                key=PreferenceKey.ATTACHED_FILE_PATH_PROMPT_PREFIX,
                value=PreferenceValueString(value="\n\nAttached files:"),
            ),
            PreferenceInput(
                key=PreferenceKey.ATTACHED_FILE_PATH_PROMPT_SEPARATOR,
                value=PreferenceValueString(value="\n"),
            ),
            PreferenceInput(
                key=PreferenceKey.NO_TOOL_RESPONSE_PROMPT,
                value=PreferenceValueString(value="<no_response>"),
            ),
            # Provider base URLs
            PreferenceInput(
                key=PreferenceKey.OPEN_AI_BASE_URL,
                value=PreferenceValueString(value="https://api.openai.com/v1"),
            ),
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_BASE_URL,
                value=PreferenceValueString(value="https://api.anthropic.com"),
            ),
            # LLM preferences
            PreferenceInput(
                key=PreferenceKey.LLM_STREAM,
                value=PreferenceValueBool(value=True),
            ),
            # Anthropic reasoning budget tokens
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_REASONING_MINIMAL_BUDGET_TOKENS,
                value=PreferenceValueInt(value=1024),
            ),
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_REASONING_LOW_BUDGET_TOKENS,
                value=PreferenceValueInt(value=4096),
            ),
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_REASONING_MEDIUM_BUDGET_TOKENS,
                value=PreferenceValueInt(value=10000),
            ),
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_REASONING_HIGH_BUDGET_TOKENS,
                value=PreferenceValueInt(value=20000),
            ),
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_REASONING_XHIGH_BUDGET_TOKENS,
                value=PreferenceValueInt(value=65536),
            ),
            # Anthropic cache TTLs
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_CACHE_MEDIUM_TTL,
                value=PreferenceValueString(value="5m"),
            ),
            PreferenceInput(
                key=PreferenceKey.ANTHROPIC_CACHE_HIGH_TTL,
                value=PreferenceValueString(value="1h"),
            ),
        ]

    @staticmethod
    def _get_system_prompt() -> str:
        return (
            "You are ALENT.RED, an agentic platform that runs on the user's own computer and "
            "helps them achieve any task or workflow end to end.\n\n"
            "Your job is to make what the user asks for actually happen. Always find a way: when "
            "a path is blocked, look for another, combine your tools, try different approaches, "
            "and keep going until the request is fully delivered. Do not stop at a partial "
            "result, a plan, or an explanation of what could be done when you can do it "
            "yourself.\n\n"
            "Work end to end and step by step: break the task down, execute each step with the "
            "tools available, check the result of every action before moving on, and recover "
            "from errors on your own. Ask the user only when a decision is genuinely theirs, "
            "when an action is hard to reverse, or when you are missing information you cannot "
            "obtain by yourself.\n\n"
            "Deliver high quality: be precise, thorough, and careful, verify your work before "
            "reporting it, and never invent a result. Be direct and concise, report what you did "
            "and what you found, and say plainly when something failed or is not supported.\n\n"
            "{{AGENT_PROMPT}}\n\n"
            "{{BRICK_PROMPT}}"
        )
