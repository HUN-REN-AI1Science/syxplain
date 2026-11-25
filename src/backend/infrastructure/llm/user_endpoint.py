"""
Live check of a user's OpenAI-compatible endpoint (key, base URL and model).
"""

from backend.utils.url_safety import UnsafeUrlError, ensure_public_http_url

# Output cap of the test request: enough for any model to answer, cheap on every price list
_PROBE_MAX_TOKENS = 16
_PROBE_TIMEOUT_S = 20.0


class EndpointCheckError(Exception):
    """The endpoint check failed; the message can be shown to the user."""


def _short(error: Exception, limit: int = 200) -> str:
    message = getattr(error, "message", None) or str(error)
    return message if len(message) <= limit else message[: limit - 3] + "..."


def check_openai_compatible_endpoint(api_key: str, api_base: str, model: str) -> None:
    """
    Send one tiny chat completion to the endpoint to check the key, base URL and model.

    The base URL must pass the SSRF check first. Blocking: call it from a worker thread.

    Raises:
        EndpointCheckError: With a message that can be shown to the user.
    """
    try:
        ensure_public_http_url(api_base)
    except UnsafeUrlError as e:
        raise EndpointCheckError(str(e))

    import openai

    client = openai.OpenAI(
        api_key=api_key,
        base_url=api_base,
        timeout=_PROBE_TIMEOUT_S,
        max_retries=0,
        # A redirect could lead past the address check above
        http_client=openai.DefaultHttpxClient(follow_redirects=False),
    )
    messages = [{"role": "user", "content": "Reply with OK."}]
    try:
        try:
            client.chat.completions.create(
                model=model, messages=messages, max_tokens=_PROBE_MAX_TOKENS
            )
        except openai.BadRequestError as e:
            # OpenAI's reasoning models refuse max_tokens and ask for max_completion_tokens
            if "max_completion_tokens" not in str(e):
                raise
            client.chat.completions.create(
                model=model, messages=messages, max_completion_tokens=_PROBE_MAX_TOKENS
            )
    except openai.AuthenticationError:
        raise EndpointCheckError(
            "The endpoint rejected the API key (401). Please check your key and try again."
        )
    except openai.PermissionDeniedError:
        raise EndpointCheckError(
            f"The API key has no access to the model '{model}' at this endpoint (403)."
        )
    except openai.NotFoundError:
        raise EndpointCheckError(
            f"The model '{model}' was not found at this endpoint (404). Check the model name, "
            "and that the base URL is the API root (it usually ends in /v1)."
        )
    except openai.RateLimitError:
        raise EndpointCheckError(
            "The endpoint rate limited the API key (429). Your account may have "
            "insufficient credits."
        )
    except openai.BadRequestError as e:
        if "model" in str(e).lower():
            raise EndpointCheckError(
                f"The endpoint does not accept the model '{model}': {_short(e)}"
            )
        raise EndpointCheckError(f"The endpoint refused the test request: {_short(e)}")
    except openai.APIConnectionError:
        # Also covers timeouts (APITimeoutError is a subclass)
        raise EndpointCheckError(
            "Could not reach the endpoint. Please check the base URL "
            "(e.g. https://api.openai.com/v1)."
        )
    except openai.APIStatusError as e:
        raise EndpointCheckError(
            f"The endpoint returned an error (HTTP {e.status_code}). Please check the base URL."
        )
    except Exception:
        raise EndpointCheckError(
            "The endpoint did not answer like an OpenAI-compatible API. "
            "Please check the base URL and model."
        )
