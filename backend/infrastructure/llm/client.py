"""
DSPy Client Factory.
"""
import dspy
from typing import Optional, Dict, Any

from backend.core.config import get_settings


def create_dspy_model(model_name: str = None, **kwargs) -> dspy.LM:
    """
    Create a standard DSPy LM client (OpenAI compatible).

    Args:
        model_name: Optional model name to override default.
        **kwargs: Additional arguments for dspy.LM

    Returns:
        Configured dspy.LM instance.

    Raises:
        ValueError: If API key is missing.
    """
    settings = get_settings().llm

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")

    effective_model = model_name or settings.openai_model_name

    return dspy.LM(
        model=f"openai/{effective_model}",
        api_key=settings.openai_api_key,
        api_base=settings.openai_api_base,
        **kwargs
    )


def create_deep_research_model(model_name: str = None) -> dspy.LM:
    """
    Create a DSPy LM client configured for Deep Research (web search).

    Args:
        model_name: Optional model name.

    Returns:
        Configured dspy.LM instance with search tools enabled.
    """
    settings = get_settings().llm

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
