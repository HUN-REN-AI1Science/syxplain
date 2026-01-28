"""
DSPy Client Factory.
"""
from typing import Optional

import dspy


from backend.core.config import get_settings


def create_dspy_model(
    model_name: str = None,
    user_api_key: Optional[str] = None,
    user_model: Optional[str] = None,
    **kwargs
) -> dspy.LM:
    """
    Create a standard DSPy LM client (OpenAI compatible).

    Args:
        model_name: Optional model name to override default (for server keys).
        user_api_key: Optional user-provided API key.
        user_model: Optional user-specified model (used with user_api_key).
        **kwargs: Additional arguments for dspy.LM

    Returns:
        Configured dspy.LM instance.

    Raises:
        ValueError: If no API key is available.
    """
    settings = get_settings().llm

    if user_api_key:
        # User-provided key: direct to OpenAI
        effective_model = user_model or "gpt-4o"
        return dspy.LM(
            model=f"openai/{effective_model}",
            api_key=user_api_key,
            api_base=None,  # Use default OpenAI endpoint
            **kwargs
        )

    # Server key: use configured proxy
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    effective_model = model_name or settings.openai_model_name

    return dspy.LM(
        model=f"openai/{effective_model}",
        api_key=settings.openai_api_key,
        api_base=settings.openai_api_base,
        **kwargs
    )


def create_deep_research_model(
    model_name: str = None,
    user_api_key: Optional[str] = None,
) -> dspy.LM:
    """
    Create a DSPy LM client configured for Deep Research (web search).

    Args:
        model_name: Optional model name (only used with server keys).
        user_api_key: Optional user-provided API key.

    Returns:
        Configured dspy.LM instance with search tools enabled.

    Raises:
        ValueError: If no API key is available.
    """
    settings = get_settings().llm

    if user_api_key:
        # User key: only o4-mini-deep-research allowed
        return dspy.LM(
            model="openai/o4-mini-deep-research",
            api_key=user_api_key,
            api_base=None,  # Use default OpenAI endpoint
            extra_body={
                "tools": [
                    {
                        "type": "web_search_preview",
                        "search_context_size": "medium"
                    }
                ]
            }
        )

    # Server key: use configured settings
    if not settings.deep_research_api_key:
        raise ValueError("DEEP_RESEARCH_API_KEY is not configured.")

    # Determine model name
    effective_model = model_name
    if not effective_model:
        # Parse from comma-separated list or fallback
        models = settings.get_deep_research_model_list()
        effective_model = models[0] if models else "o4-mini-deep-research"

    return dspy.LM(
        model=f"openai/{effective_model}",
        api_key=settings.deep_research_api_key,
        api_base=settings.deep_research_api_base,
        extra_body={
            "tools": [
                {
                    "type": "web_search_preview",
                    "search_context_size": "medium"
                }
            ]
        }
    )
