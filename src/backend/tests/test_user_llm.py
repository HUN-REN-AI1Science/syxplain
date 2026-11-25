"""A user's own LLM: Gemini or any OpenAI-compatible endpoint (schemas, routing, SSRF)."""

import socket
from unittest.mock import MagicMock

import httpx
import openai
import pytest
from pydantic import ValidationError

from backend.core.config import get_settings
from backend.core.exceptions import ValidationError as AppValidationError
from backend.infrastructure.llm import user_endpoint
from backend.infrastructure.llm.client import create_dspy_model
from backend.infrastructure.llm.user_endpoint import (
    EndpointCheckError,
    check_openai_compatible_endpoint,
)
from backend.schemas.programmatic import AnalyzeParams
from backend.schemas.requests import (
    SuggestDescriptionsRequest,
    UserApiKeys,
    ValidateKeysRequest,
)
from backend.utils.url_safety import UnsafeUrlError, ensure_public_http_url
from backend.utils.user_llm import (
    OPENAI_DEFAULT_API_BASE,
    UserLLM,
    is_official_openai_base,
    resolve_literature_key,
)

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


def test_legacy_gemini_fields_fill_the_generic_ones():
    keys = UserApiKeys(gemini_api_key="AIza-key", gemini_model="gemini-2.5-pro")
    assert keys.provider == "gemini"
    assert keys.api_key == "AIza-key"
    assert keys.model == "gemini-2.5-pro"
    assert keys.api_base is None

    # The generic fields win over the legacy ones
    keys = UserApiKeys(api_key="AIza-new", gemini_api_key="AIza-old", model="m")
    assert (keys.api_key, keys.model) == ("AIza-new", "m")


def test_gemini_ignores_a_base_url_and_leaves_the_model_to_the_client_default():
    keys = UserApiKeys(api_key="AIza-key", api_base="https://example.com/v1")
    assert keys.api_base is None
    assert keys.model is None  # create_dspy_model falls back to the first offered model


def test_user_api_keys_requires_a_key():
    with pytest.raises(ValidationError):
        UserApiKeys()
    with pytest.raises(ValidationError):
        UserApiKeys(provider="openai_compatible", api_key="  ", model="gpt-5")


def test_openai_compatible_defaults_to_the_openai_base():
    keys = UserApiKeys(provider="openai_compatible", api_key="sk-x", model="gpt-5")
    assert keys.api_base == OPENAI_DEFAULT_API_BASE
    keys = UserApiKeys(provider="openai_compatible", api_key="sk-x", model="gpt-5", api_base=" ")
    assert keys.api_base == OPENAI_DEFAULT_API_BASE


def test_openai_compatible_base_is_trimmed():
    keys = UserApiKeys(
        provider="openai_compatible",
        api_key="sk-or-x",
        model=" openai/gpt-5 ",
        api_base=" https://openrouter.ai/api/v1/ ",
    )
    assert keys.api_base == "https://openrouter.ai/api/v1"
    assert keys.model == "openai/gpt-5"


@pytest.mark.parametrize(
    "base", ["ftp://example.com/v1", "example.com/v1", "https://", "file:///etc/passwd"]
)
def test_openai_compatible_base_must_be_http(base):
    with pytest.raises(ValidationError):
        UserApiKeys(provider="openai_compatible", api_key="sk-x", model="gpt-5", api_base=base)


def test_openai_compatible_requires_a_model():
    with pytest.raises(ValidationError, match="model is required"):
        UserApiKeys(provider="openai_compatible", api_key="sk-x")


def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError):
        UserApiKeys(provider="anthropic", api_key="x")


def test_suggestion_and_validation_bodies_carry_optional_keys():
    body = SuggestDescriptionsRequest(project_description="Soil phosphorus study", columns=["pH"])
    assert body.api_key is None and body.provider == "gemini"

    body = SuggestDescriptionsRequest(
        project_description="Soil phosphorus study",
        columns=["pH"],
        gemini_api_key="AIza-key",
        gemini_model="gemini-2.5-flash",
    )
    assert (body.api_key, body.model) == ("AIza-key", "gemini-2.5-flash")

    body = ValidateKeysRequest(openai_api_key="sk-lit")
    assert body.api_key is None and body.openai_api_key == "sk-lit"


def test_programmatic_params_accept_legacy_and_generic_fields():
    base = {"project_description": "p", "target_variable": "y", "features": {"x": "x"}}
    legacy = AnalyzeParams(**base, gemini_api_key="AIza-key", gemini_model="gemini-2.5-pro")
    assert legacy.to_user_llm() == UserLLM(api_key="AIza-key", model="gemini-2.5-pro")

    params = AnalyzeParams(
        **base,
        provider="openai_compatible",
        api_key="sk-or-x",
        model="openai/gpt-5",
        api_base="https://openrouter.ai/api/v1",
    )
    user_llm = params.to_user_llm()
    assert user_llm.api_base == "https://openrouter.ai/api/v1"
    assert user_llm.openai_key is None  # not OpenAI's endpoint: no literature search

    # Users with server-key access send no key at all
    assert AnalyzeParams(**base).api_key is None


# ---------------------------------------------------------------------------
# Literature-key resolution
# ---------------------------------------------------------------------------


def test_official_openai_base_detection():
    assert is_official_openai_base("https://api.openai.com/v1")
    assert is_official_openai_base("https://API.openai.com/v1/")
    assert not is_official_openai_base("http://api.openai.com/v1")
    assert not is_official_openai_base("https://api.openai.com.evil.example/v1")
    assert not is_official_openai_base("https://openrouter.ai/api/v1")
    assert not is_official_openai_base(None)


def test_literature_key_resolution():
    openai_base = OPENAI_DEFAULT_API_BASE
    # A main key on OpenAI's own endpoint doubles as the literature key
    assert resolve_literature_key("sk-main", openai_base, None) == "sk-main"
    # A separate key always wins
    assert resolve_literature_key("sk-main", openai_base, "sk-lit") == "sk-lit"
    assert resolve_literature_key("sk-or", "https://openrouter.ai/api/v1", "sk-lit") == "sk-lit"
    # Any other endpoint, or Gemini, needs the separate key
    assert resolve_literature_key("sk-or", "https://openrouter.ai/api/v1", None) is None
    assert resolve_literature_key("AIza-key", None, None) is None


def test_schema_resolves_the_literature_key():
    keys = UserApiKeys(provider="openai_compatible", api_key="sk-main", model="gpt-5")
    assert keys.to_user_llm().openai_key == "sk-main"

    keys = UserApiKeys(
        provider="openai_compatible", api_key="sk-main", model="gpt-5", openai_api_key="sk-lit"
    )
    assert keys.to_user_llm().openai_key == "sk-lit"

    keys = UserApiKeys(gemini_api_key="AIza-key")
    assert keys.to_user_llm().openai_key is None
    keys = UserApiKeys(gemini_api_key="AIza-key", openai_api_key="sk-lit")
    assert keys.to_user_llm().openai_key == "sk-lit"


def test_user_llm_hides_keys_from_repr():
    user_llm = UserLLM(api_key="sk-secret", model="gpt-5", openai_key="sk-lit")
    assert "sk-secret" not in repr(user_llm) and "sk-lit" not in repr(user_llm)


def test_user_llm_redacts_its_secrets():
    user_llm = UserLLM(api_key="sk-secret", api_base="https://llm.example.com/v1")
    out = user_llm.redact("POST https://llm.example.com/v1 with sk-secret failed")
    assert "sk-secret" not in out and "llm.example.com" not in out
    assert UserLLM().redact("nothing to hide") == "nothing to hide"


def test_user_facing_errors_are_redacted():
    from backend.services.orchestrator_service import _format_user_facing_error

    user_llm = UserLLM(api_key="sk-secret", api_base="https://llm.example.com/v1")
    message = _format_user_facing_error(RuntimeError("sk-secret rejected"), user_llm)
    assert "sk-secret" not in message


def test_small_model():
    assert (
        UserLLM(api_key="k", model="gpt-5", api_base="https://x.io/v1").small_model("s") == "gpt-5"
    )
    assert UserLLM(api_key="k").small_model("small") == "small"
    assert UserLLM(api_key="k", model="gemini-2.5-pro").small_model("small") == "gemini-2.5-pro"


# ---------------------------------------------------------------------------
# create_dspy_model routing (no network)
# ---------------------------------------------------------------------------


def test_user_endpoint_routes_through_the_openai_provider():
    lm = create_dspy_model(
        user_llm=UserLLM(
            api_key="sk-user",
            model="meta-llama/Llama-3.3-70B-Instruct",
            api_base="https://llm.example.com/v1",
        ),
        cache_key="ignored-for-user-endpoints",
    )
    assert lm.model == "openai/meta-llama/Llama-3.3-70B-Instruct"
    assert lm.kwargs["api_key"] == "sk-user"
    assert lm.kwargs["api_base"] == "https://llm.example.com/v1"
    assert "prompt_cache_key" not in lm.kwargs


def test_user_key_without_base_routes_through_gemini():
    lm = create_dspy_model(user_llm=UserLLM(api_key="AIza-key", model="gemini-2.5-pro"))
    assert lm.model == "gemini/gemini-2.5-pro"
    assert lm.kwargs["api_key"] == "AIza-key"
    assert "api_base" not in lm.kwargs

    lm = create_dspy_model(user_llm=UserLLM(api_key="AIza-key"))
    first_offered = get_settings().llm.get_user_api_model_list()[0]
    assert lm.model == f"gemini/{first_offered}"


def test_user_endpoint_needs_a_model():
    with pytest.raises(ValueError):
        create_dspy_model(
            user_llm=UserLLM(api_key="sk-user", api_base="https://llm.example.com/v1")
        )


def test_discovery_lm_follows_the_context(monkeypatch):
    import pandas as pd

    from backend.services.orchestrator_service import AnalysisContext, AnalysisOrchestrator

    context = AnalysisContext(
        run_id="r",
        user_id="u",
        problem_description={},
        data=pd.DataFrame(),
        target_column="y",
        predictor_columns=[],
        user_llm=UserLLM(api_key="sk-user", model="gpt-5", api_base="https://api.openai.com/v1"),
    )
    lm = AnalysisOrchestrator._discovery_lm(MagicMock(), context, "server-model")
    assert lm.model == "openai/gpt-5"
    assert lm.kwargs["api_base"] == "https://api.openai.com/v1"


def test_suggestions_use_the_chosen_model_on_a_user_endpoint(monkeypatch):
    from backend.services import llm_service

    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("stop")

    monkeypatch.setattr(llm_service, "create_dspy_model", fake_create)
    small = llm_service.get_settings().llm.small_user_model_name

    for user_llm in [
        UserLLM(api_key="sk-user", model="gpt-5", api_base="https://api.openai.com/v1"),
        UserLLM(api_key="AIza-key"),
        UserLLM(api_key="AIza-key", model="gemini-2.5-pro"),
    ]:
        with pytest.raises(RuntimeError):
            llm_service.guess_column_descriptions_batch("p", "y", ["x"], user_llm)

    assert [c["user_llm"].model for c in calls] == ["gpt-5", small, "gemini-2.5-pro"]
    assert calls[0]["user_llm"].api_base == "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# SSRF guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/v1",
        "http://localhost/v1",
        "http://10.0.0.5/v1",
        "http://172.16.3.4/v1",
        "http://172.31.255.255/v1",
        "http://192.168.1.10/v1",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0:8080/v1",
        "http://100.64.0.1/v1",
        "http://[::1]:8000/v1",
        "http://[fc00::1]/v1",
        "http://[fd12:3456::1]/v1",
        "http://[fe80::1]/v1",
        "http://[::ffff:127.0.0.1]/v1",
    ],
)
def test_private_and_local_addresses_are_rejected(url):
    with pytest.raises(UnsafeUrlError, match="private, local or reserved"):
        ensure_public_http_url(url)


def _resolver(*addresses):
    def resolve(host, port):
        return [
            (
                socket.AF_INET6 if ":" in a else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (a, port, 0, 0) if ":" in a else (a, port),
            )
            for a in addresses
        ]

    return resolve


def test_public_addresses_pass():
    ensure_public_http_url("https://8.8.8.8/v1")
    ensure_public_http_url("https://[2606:4700:4700::1111]/v1")
    ensure_public_http_url("https://llm.example.com/v1", resolve=_resolver("93.184.216.34"))


def test_a_host_resolving_to_a_private_address_is_rejected():
    with pytest.raises(UnsafeUrlError):
        ensure_public_http_url("https://evil.example/v1", resolve=_resolver("10.1.2.3"))
    # Any private answer among public ones is enough
    with pytest.raises(UnsafeUrlError):
        ensure_public_http_url(
            "https://evil.example/v1", resolve=_resolver("93.184.216.34", "127.0.0.1")
        )
    with pytest.raises(UnsafeUrlError):
        ensure_public_http_url("https://metadata.example/v1", resolve=_resolver("169.254.169.254"))


def test_unresolvable_and_non_http_urls_are_rejected():
    def fail(host, port):
        raise socket.gaierror("no such host")

    with pytest.raises(UnsafeUrlError, match="Could not resolve"):
        ensure_public_http_url("https://nope.invalid/v1", resolve=fail)
    for url in ["ftp://8.8.8.8/", "gopher://8.8.8.8/", "8.8.8.8/v1", "http://", "http://[::1"]:
        with pytest.raises(UnsafeUrlError):
            ensure_public_http_url(url)


def test_run_validation_rejects_a_private_base():
    from backend.services.run_service import RunService

    file_repo = MagicMock()
    service = RunService(MagicMock(), file_repo, MagicMock(), file_service=MagicMock())
    with pytest.raises(AppValidationError, match="private, local or reserved"):
        service.validate_run_request(
            csv_filename="data.csv",
            target_variable="y",
            features={"x": "x"},
            user_id="00000000-0000-0000-0000-000000000001",
            has_server_keys_access=False,
            user_llm=UserLLM(api_key="sk-user", model="m", api_base="http://169.254.169.254/v1"),
        )
    file_repo.get_latest_by_filename.assert_not_called()


# ---------------------------------------------------------------------------
# Endpoint check (validate-keys), with a fake OpenAI client
# ---------------------------------------------------------------------------


def test_endpoint_check_refuses_a_private_base_before_any_request(monkeypatch):
    client_factory = MagicMock()
    monkeypatch.setattr(openai, "OpenAI", client_factory)
    with pytest.raises(EndpointCheckError, match="private, local or reserved"):
        check_openai_compatible_endpoint("sk-user", "http://127.0.0.1:11434/v1", "llama3")
    client_factory.assert_not_called()


def _status_error(cls, status: int, message: str):
    request = httpx.Request("POST", "https://8.8.8.8/v1/chat/completions")
    return cls(message, response=httpx.Response(status, request=request), body=None)


def _fake_client(monkeypatch, *effects):
    client = MagicMock()
    client.chat.completions.create.side_effect = list(effects)
    monkeypatch.setattr(openai, "OpenAI", MagicMock(return_value=client))
    return client


def test_endpoint_check_passes_and_retries_with_max_completion_tokens(monkeypatch):
    client = _fake_client(
        monkeypatch,
        _status_error(
            openai.BadRequestError,
            400,
            "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead.",
        ),
        MagicMock(),
    )
    check_openai_compatible_endpoint("sk-user", "https://8.8.8.8/v1", "gpt-5")
    first, second = client.chat.completions.create.call_args_list
    assert "max_tokens" in first.kwargs and "max_completion_tokens" in second.kwargs


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_status_error(openai.AuthenticationError, 401, "bad key"), "401"),
        (_status_error(openai.NotFoundError, 404, "no such model"), "not found"),
        (_status_error(openai.BadRequestError, 400, "x is not a valid model ID"), "model"),
        (_status_error(openai.RateLimitError, 429, "slow down"), "429"),
        (
            openai.APIConnectionError(request=httpx.Request("POST", "https://8.8.8.8")),
            "Could not reach",
        ),
    ],
)
def test_endpoint_check_explains_failures(monkeypatch, error, expected):
    _fake_client(monkeypatch, error)
    with pytest.raises(EndpointCheckError, match=expected) as info:
        check_openai_compatible_endpoint("sk-user", "https://8.8.8.8/v1", "gpt-x")
    assert "sk-user" not in str(info.value)


def test_endpoint_check_module_does_not_follow_redirects(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(openai, "OpenAI", factory)
    check_openai_compatible_endpoint("sk-user", "https://8.8.8.8/v1", "gpt-5")
    http_client = factory.call_args.kwargs["http_client"]
    assert http_client.follow_redirects is False
    assert user_endpoint._PROBE_MAX_TOKENS <= 32
