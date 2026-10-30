"""
DSPy Client Factory.
"""

import dspy

from backend.core.config import get_settings
from backend.utils.user_llm import UserLLM


def create_dspy_model(
    model_name: str | None = None,
    user_llm: UserLLM | None = None,
    cache_key: str | None = None,
    **kwargs,
) -> dspy.LM:
    """
    Create a standard DSPy LM client.

    User-provided keys route to the user's OpenAI-compatible endpoint when it has a
    base URL, and to Gemini otherwise; server keys route through the configured
    OpenAI-compatible proxy.

    Args:
        model_name: Optional model name to override default (for server keys).
        user_llm: The user's own LLM settings; empty or None means the server keys.
        cache_key: OpenAI prompt-cache routing key for calls that share a long prefix
            (best-effort; prompts carrying images were often not served from cache).
            Server keys only: other endpoints may reject the unknown parameter.
        **kwargs: Additional arguments for dspy.LM

    Returns:
        Configured dspy.LM instance.

    Raises:
        ValueError: If no API key is available, or no model for a user endpoint.
    """
    settings = get_settings().llm

    if user_llm and user_llm.api_key and user_llm.api_base:
        # User-provided key on their own OpenAI-compatible endpoint
        if not user_llm.model:
            raise ValueError("A model is required for an OpenAI-compatible endpoint.")
        return dspy.LM(
            model=f"openai/{user_llm.model}",
            api_key=user_llm.api_key,
            api_base=user_llm.api_base,
            **kwargs,
        )

    if user_llm and user_llm.api_key:
        # User-provided key: route through Gemini (the first offered model by default)
        effective_model = user_llm.model or settings.get_user_api_model_list()[0]
        return dspy.LM(
            model=f"gemini/{effective_model}",
            api_key=user_llm.api_key,
            **kwargs,
        )

    # Server key: use configured proxy
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    effective_model = model_name or settings.openai_model_name

    if cache_key:
        kwargs["prompt_cache_key"] = cache_key
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
# The orchestrator waits this long for the search; the request gives up at the same point,
# so an abandoned search does not keep running (and billing) in its thread
LITERATURE_TIMEOUT_S = 900


def literature_available(user_llm: UserLLM | None) -> bool:
    """Server keys always search the literature; a user's own keys need an OpenAI key."""
    if user_llm and user_llm.api_key:
        return bool(user_llm.openai_key)
    return bool(get_settings().llm.openai_api_key)


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
    research_kwargs = {
        "model_type": "responses",
        "tools": [{"type": "web_search", "search_context_size": "high"}],
        "max_tool_calls": _LITERATURE_MAX_TOOL_CALLS,
        "reasoning": {"effort": "high"},
        "timeout": LITERATURE_TIMEOUT_S,
        "num_retries": 0,  # a retry could not finish within the wait anyway
        # OPENAI_MODEL_NAME may be a non-reasoning model (gpt-4o), which rejects
        # reasoning.effort; drop what the model does not support instead of failing
        "drop_params": True,
    }
    if user_api_key:
        return dspy.LM(
            model=f"openai/{_DEFAULT_LITERATURE_MODEL}",
            api_key=user_api_key,
            api_base=None,  # Use default OpenAI endpoint
            **research_kwargs,
        )
    return create_dspy_model(**research_kwargs)
