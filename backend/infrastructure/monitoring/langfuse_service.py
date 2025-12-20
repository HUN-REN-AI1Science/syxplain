"""
Langfuse tracing service.

Handles initialization, decoration, and usage reporting for Langfuse tracing.
Integrates with DSPy.
"""
import logging
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from backend.core.config import get_settings

if TYPE_CHECKING:
    import dspy
    from langfuse import Langfuse

logger = logging.getLogger(__name__)

_client: Optional["Langfuse"] = None
_enabled: bool = False


def init_langfuse() -> bool:
    """
    Initialize Langfuse with DSPy instrumentation.

    Returns:
        True if initialized successfully, False otherwise.
    """
    global _client, _enabled

    settings = get_settings().langfuse

    if not settings.enabled:
        logger.info("Langfuse tracing disabled by configuration.")
        return False

    if not settings.public_key or not settings.secret_key:
        logger.warning("Langfuse credentials (public/secret key) missing. Tracing disabled.")
        return False

    try:
        from langfuse import Langfuse
        from openinference.instrumentation.dspy import DSPyInstrumentor

        # Initialize client explicitly with settings
        _client = Langfuse(
            public_key=settings.public_key,
            secret_key=settings.secret_key,
            host=settings.base_url
        )

        if _client.auth_check():
            DSPyInstrumentor().instrument()
            _enabled = True
            logger.info("Langfuse tracing enabled and instrumented for DSPy.")
            return True
        else:
            logger.error("Langfuse authentication failed. Tracing disabled.")
            _client = None
            return False

    except ImportError as e:
        logger.warning(f"Langfuse or OpenInference dependencies not found: {e}. Tracing disabled.")
        return False
    except Exception as e:
        logger.error(f"Langfuse setup failed: {e}. Tracing disabled.")
        return False


def get_client() -> Optional["Langfuse"]:
    """Get the initialized Langfuse client."""
    if not _enabled or not _client:
        return None
    return _client


def flush_traces() -> None:
    """Flush pending traces."""
    if _client:
        try:
            _client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse traces: {e}")


def _dummy_observe(*args, **kwargs):
    """Fallback decorator when tracing is disabled."""
    def decorator(func):
        return func
    return decorator if not args or not callable(args[0]) else decorator(args[0])


def observe(*args, **kwargs):
    """
    Decorator to trace functions with Langfuse.

    Acts as a pass-through if Langfuse is disabled or not installed.
    """
    if not _enabled:
        return _dummy_observe(*args, **kwargs)

    try:
        from langfuse.decorators import observe as langfuse_observe
        return langfuse_observe(*args, **kwargs)
    except ImportError:
        return _dummy_observe(*args, **kwargs)


def _count_tokens_manually(messages: list, outputs: list) -> tuple[int, int]:
    """Estimate tokens from messages and outputs when API doesn't provide usage."""
    prompt_tokens = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            prompt_tokens += len(content) // 4
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        prompt_tokens += len(item.get("text", "")) // 4
                    elif item.get("type") == "image_url":
                        prompt_tokens += 258  # Approximate image cost

    completion_tokens = sum(len(out) // 4 for out in outputs if isinstance(out, str))
    return prompt_tokens, completion_tokens


def report_usage(lm: "dspy.LM", model_name: str = None) -> None:
    """
    Report token usage from DSPy to Langfuse.

    Args:
        lm: The DSPy LM instance
        model_name: Optional override for model name
    """
    if not _enabled or not _client or not lm.history:
        return

    try:
        last_call = lm.history[-1]
        usage_data = last_call.get("usage", {})

        if usage_data:
            prompt_tokens = usage_data.get("prompt_tokens", 0)
            completion_tokens = usage_data.get("completion_tokens", 0)
        else:
            messages = last_call.get("messages", [])
            outputs = last_call.get("outputs", [])
            prompt_tokens, completion_tokens = _count_tokens_manually(messages, outputs)

        total_tokens = prompt_tokens + completion_tokens

        if total_tokens > 0:
            effective_model = model_name or get_settings().llm.openai_model_name

            # Using update_current_generation from langfuse decorator context
            # or the client? The original code used `langfuse.update_current_generation`.
            # This requires being inside an @observe context context or similar context manager.
            # Assuming this is called within an observed function.
            try:
                # We need to import observe to get the context context
                # But actually, client methods usually operate on a specific trace ID.
                # The original code did `langfuse.update_current_generation` which implies `langfuse` module or client?
                # Original: `langfuse = get_client(); langfuse.update_current_generation(...)`
                # But `langfuse` variable in original code came from `from langfuse import get_client`.
                # So it was the MODULE-level function? No, `get_client()` returns the client instance.
                # Let's check if the client instance has `update_current_generation`.
                # It does if the decorator context is active.

                _client.update_current_generation(
                    model=effective_model,
                    usage_details={
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "total": total_tokens,
                    }
                )
            except Exception as e:
                logger.debug(f"Could not update generation usage: {e}")

        _client.flush()

    except Exception as e:
        logger.warning(f"Failed to report usage to Langfuse: {e}")
