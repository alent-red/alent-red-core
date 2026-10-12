from pydantic import BaseModel, Field


class LlmUsage(BaseModel):
    """Token usage of one LLM call, normalized across providers.

    input_tokens_count is the whole prompt the model received, prompt-cache reads and
    writes included: Anthropic reports cached tokens apart from input_tokens while
    OpenAI counts them inside, so adapters reconcile before building this model.
    """

    input_tokens_count: int = Field(ge=0)
    output_tokens_count: int = Field(ge=0)
