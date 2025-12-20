"""Langfuse configuration and tracing utilities for DSPy."""
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import dspy

# Re-export observe decorator for convenience
_public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
_secret_key = os.environ.get("LANGFUSE_SECRET_KEY")

if _public_key and _secret_key:
    try:
        from langfuse import observe, get_client
    except ImportError:
        _public_key = None  # Force usage of dummy implementation below

if not _public_key or not _secret_key:
    def observe(*args, **kwargs):
        def decorator(func):
            return func
        return decorator if not args or not callable(args[0]) else decorator(args[0])

    def get_client():
        return None

_langfuse_enabled = False
_langfuse_client = None


def init_langfuse():
    """Initialize Langfuse with OpenInference DSPy instrumentation."""
    global _langfuse_enabled, _langfuse_client

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        print("Langfuse credentials not configured. Tracing disabled.")
        return False

    try:
        from langfuse import get_client
        from openinference.instrumentation.dspy import DSPyInstrumentor

        _langfuse_client = get_client()
        if _langfuse_client.auth_check():
            DSPyInstrumentor().instrument()
            _langfuse_enabled = True
            print("Langfuse tracing enabled for DSPy.")
            return True
        else:
            print("Langfuse authentication failed. Tracing disabled.")
            return False
    except ImportError as e:
        print(f"Langfuse/OpenInference import failed: {e}. Tracing disabled.")
        return False
    except Exception as e:
        print(f"Langfuse setup failed: {e}. Tracing disabled.")
        return False


def is_langfuse_enabled() -> bool:
    """Check if Langfuse tracing is enabled."""
    return _langfuse_enabled


def flush_traces():
    """Flush any pending Langfuse traces."""
    if _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception:
            pass


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
                        prompt_tokens += 258  # Gemini image token cost
    completion_tokens = sum(len(out) // 4 for out in outputs if isinstance(out, str))
    return prompt_tokens, completion_tokens


def report_usage_to_langfuse(lm: "dspy.LM") -> None:
    """Extract token usage from DSPy LM history and report to Langfuse."""
    if not is_langfuse_enabled() or not lm.history:
        return

    langfuse = get_client()
    if langfuse is None:
        return

    last_call = lm.history[-1]
    usage_data = last_call.get("usage", {})

    if usage_data:
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)
    else:
        # Manually calculate from messages and outputs if usage not provided
        messages = last_call.get("messages", [])
        outputs = last_call.get("outputs", [])
        prompt_tokens, completion_tokens = _count_tokens_manually(messages, outputs)

    total_tokens = prompt_tokens + completion_tokens

    if total_tokens > 0:
        model_name = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o")
        langfuse.update_current_generation(
            model=model_name,
            usage_details={
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": total_tokens,
            }
        )
    langfuse.flush()


# Initialize on module load
init_langfuse()
