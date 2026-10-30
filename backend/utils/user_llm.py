"""
The LLM settings of a user who brings their own key (users without HUN-REN access).

A user picks a provider: Google Gemini, or any endpoint that speaks the OpenAI API
(OpenAI itself, OpenRouter, vLLM, LiteLLM, ...). The settings live only in memory for
the request or run; they are never stored and never logged.
"""

from dataclasses import dataclass, field
from typing import Literal

from backend.utils.url_safety import parse_http_url

LLMProvider = Literal["gemini", "openai_compatible"]

OPENAI_DEFAULT_API_BASE = "https://api.openai.com/v1"
_OPENAI_HOST = "api.openai.com"


def normalize_api_base(api_base: str | None) -> str:
    """The base URL of an OpenAI-compatible endpoint: OpenAI's when empty, http(s) only."""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        return OPENAI_DEFAULT_API_BASE
    parse_http_url(base)
    return base


def is_official_openai_base(api_base: str | None) -> bool:
    """Whether a normalized base URL is OpenAI's own API (the only one with web search)."""
    if not api_base:
        return False
    parts = parse_http_url(api_base)
    return parts.scheme == "https" and parts.hostname.lower() == _OPENAI_HOST


def resolve_literature_key(
    api_key: str | None, api_base: str | None, openai_api_key: str | None
) -> str | None:
    """
    The OpenAI key for the literature search, which needs OpenAI's Responses API with
    web search. A separate key wins; otherwise a main key on OpenAI's own endpoint
    doubles as the literature key. Any other endpoint gets no literature search.
    """
    if openai_api_key:
        return openai_api_key
    if api_key and is_official_openai_base(api_base):
        return api_key
    return None


@dataclass(frozen=True)
class UserLLM:
    """
    A user's own LLM settings, passed down to the run as one value (keys hidden from
    repr). Empty (no api_key) for users on the server keys.
    """

    api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    # Set only for an OpenAI-compatible endpoint; None means Gemini
    api_base: str | None = None
    # The literature-search key, already resolved (see resolve_literature_key)
    openai_key: str | None = field(default=None, repr=False)

    def small_model(self, gemini_default: str) -> str | None:
        """The model for lightweight tasks: the chosen one on a user's own endpoint."""
        return self.model if self.api_base else (self.model or gemini_default)

    def redact(self, text: str) -> str:
        """Remove the keys and base URL from text bound for the database or the user."""
        for secret in (self.api_key, self.openai_key, self.api_base):
            if secret:
                text = text.replace(secret, "[redacted]")
        return text
