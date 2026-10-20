"""
DSPy Client Factory.
"""

import dspy

from backend.core.config import get_settings


def create_dspy_model(
    model_name: str | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
    **kwargs,
) -> dspy.LM:
    """
    Create a standard DSPy LM client.

    User-provided keys route through Gemini; server keys route through
    the configured OpenAI-compatible proxy.

    Args:
        model_name: Optional model name to override default (for server keys).
        user_api_key: Optional user-provided Gemini API key.
        user_model: Optional user-specified Gemini model (used with user_api_key).
        **kwargs: Additional arguments for dspy.LM

    Returns:
        Configured dspy.LM instance.

    Raises:
        ValueError: If no API key is available.
    """
    settings = get_settings().llm

    if user_api_key:
        # User-provided key: route through Gemini
        effective_model = user_model or "gemini-3.1-pro-preview"
        return dspy.LM(
            model=f"gemini/{effective_model}",
            api_key=user_api_key,
            **kwargs,
        )

    # Server key: use configured proxy
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    effective_model = model_name or settings.openai_model_name

    return dspy.LM(
        model=f"openai/{effective_model}",
        api_key=settings.openai_api_key,
        api_base=settings.openai_api_base,
        **kwargs,
    )


# Model for the literature search on a user's own OpenAI key (server keys use OPENAI_MODEL_NAME)
_DEFAULT_LITERATURE_MODEL = "gpt-6.1-sol"
# Web searches per literature search: the main cost and latency lever
_LITERATURE_MAX_TOOL_CALLS = 60


def create_literature_model(user_api_key: str | None = None) -> dspy.LM:
    """
    The main model, set up to search the literature on the web as broadly as the retired
    deep-research models did: the Responses API web-search tool (Chat Completions accepts
    only function tools) with the largest search context and high reasoning effort.

    Args:
        user_api_key: Optional user-provided OpenAI API key.

    Raises:
        ValueError: If no API key is available.
    """
    settings = get_settings().llm
    research_kwargs = {
        "model_type": "responses",
        "tools": [{"type": "web_search", "search_context_size": "high"}],
        "max_tool_calls": _LITERATURE_MAX_TOOL_CALLS,
        "reasoning": {"effort": "high"},
        "timeout": 1800,
    }
    if user_api_key:
        return dspy.LM(
            model=f"openai/{_DEFAULT_LITERATURE_MODEL}",
            api_key=user_api_key,
            api_base=None,  # Use default OpenAI endpoint
            **research_kwargs,
        )
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")
    return dspy.LM(
        model=f"openai/{settings.openai_model_name}",
        api_key=settings.openai_api_key,
        api_base=settings.openai_api_base,
        **research_kwargs,
    )
