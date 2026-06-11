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


_DEFAULT_DEEP_RESEARCH_MODEL = "o4-mini-deep-research"


def create_deep_research_model(
    model_name: str | None = None,
    user_api_key: str | None = None,
) -> dspy.LM:
    """
    Create a DSPy LM client configured for Deep Research (web search).

    Args:
        model_name: Optional model name override.
        user_api_key: Optional user-provided OpenAI API key.

    Returns:
        Configured dspy.LM instance with search tools enabled.

    Raises:
        ValueError: If no API key is available.
    """
    settings = get_settings().llm

    # Deep research models require at least one of web_search_preview/mcp/file_search.
    extra_body = {"tools": [{"type": "web_search_preview", "search_context_size": "medium"}]}

    if user_api_key:
        # User key: direct to OpenAI with selected model
        return dspy.LM(
            model=f"openai/{model_name or _DEFAULT_DEEP_RESEARCH_MODEL}",
            api_key=user_api_key,
            api_base=None,  # Use default OpenAI endpoint
            extra_body=extra_body,
        )

    # Server key: use configured settings
    if not settings.deep_research_api_key:
        raise ValueError("DEEP_RESEARCH_API_KEY is not configured.")

    # Determine model name
    effective_model = model_name
    if not effective_model:
        # Parse from comma-separated list or fallback
        models = settings.get_deep_research_model_list()
        effective_model = models[0] if models else _DEFAULT_DEEP_RESEARCH_MODEL

    return dspy.LM(
        model=f"openai/{effective_model}",
        api_key=settings.deep_research_api_key,
        api_base=settings.deep_research_api_base,
        extra_body=extra_body,
    )
