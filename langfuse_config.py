"""Langfuse configuration and tracing utilities for DSPy."""
import os

# Try to initialize Langfuse OpenInference instrumentation
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
        except Exception as e:
            print(f"Failed to flush Langfuse traces: {e}")


# Initialize on module load
init_langfuse()
