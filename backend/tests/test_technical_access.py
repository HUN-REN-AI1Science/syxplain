"""Technical (service-account) access: token checks, identity, limits."""

import asyncio

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from backend.api.routers.profile import delete_profile
from backend.core import security
from backend.core.config import AuthSettings
from backend.core.rate_limit import rate_limit_key
from backend.core.security import User, check_token_claims

SUB = "00000000-0000-0000-0000-000000000002"


def _settings(allowed: str = "") -> AuthSettings:
    settings = AuthSettings()
    settings.allowed_clients = allowed
    return settings


def _authenticate(monkeypatch, payload: dict) -> User:
    monkeypatch.setattr(security, "decode_jwt_token", lambda token, settings: payload)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    return security._authenticate_jwt(credentials, _settings())


def _request(path: str, headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request(
        {"type": "http", "method": "GET", "path": path, "headers": raw, "client": ("10.0.0.9", 1)}
    )


# ---------------------------------------------------------------------------
# Token claims
# ---------------------------------------------------------------------------


def test_only_access_tokens_authenticate():
    check_token_claims({"typ": "Bearer", "azp": "syxplain-frontend"}, _settings())
    check_token_claims({"azp": "syxplain-frontend"}, _settings())  # typ is optional
    for token_type in ("ID", "Refresh", "Offline"):
        with pytest.raises(jwt.InvalidTokenError, match="not an access token"):
            check_token_claims({"typ": token_type}, _settings())


def test_client_allow_list_is_enforced_when_set():
    allowed = _settings("syxplain-frontend, adp-librechat")
    check_token_claims({"typ": "Bearer", "azp": "adp-librechat"}, allowed)
    with pytest.raises(jwt.InvalidTokenError, match="client not allowed"):
        check_token_claims({"typ": "Bearer", "azp": "another-app"}, allowed)
    with pytest.raises(jwt.InvalidTokenError, match="client not allowed"):
        check_token_claims({"typ": "Bearer"}, allowed)
    # No list configured: any client of the realm
    check_token_claims({"typ": "Bearer", "azp": "another-app"}, _settings())


# ---------------------------------------------------------------------------
# Service-account identity
# ---------------------------------------------------------------------------


def test_service_account_gets_its_username_as_identity(monkeypatch):
    user = _authenticate(
        monkeypatch,
        {
            "sub": SUB,
            "preferred_username": "service-account-adp-librechat",
            "realm_access": {"roles": ["server-llm-access"]},
        },
    )
    assert user.email == "service-account-adp-librechat"
    assert user.is_service_account and user.has_server_keys_access and not user.is_admin


def test_people_are_not_service_accounts(monkeypatch):
    user = _authenticate(
        monkeypatch,
        {"sub": SUB, "email": "a@b.hu", "email_verified": True, "preferred_username": "a@b.hu"},
    )
    assert user.email == "a@b.hu" and not user.is_service_account
    # A token without email that is not a service account keeps no identity
    anonymous = _authenticate(monkeypatch, {"sub": SUB, "preferred_username": "someone"})
    assert anonymous.email is None and not anonymous.is_service_account


def test_service_account_cannot_delete_its_profile():
    class Service:
        async def delete_account(self, user_id):
            raise AssertionError("must not be called")

    account = User(SUB, "service-account-adp-librechat", [])
    with pytest.raises(HTTPException) as e:
        asyncio.run(delete_profile(current_user=account, profile_service=Service()))
    assert e.value.status_code == 403


# ---------------------------------------------------------------------------
# Rate-limit key
# ---------------------------------------------------------------------------


def test_programmatic_requests_are_limited_per_credential():
    a = rate_limit_key(_request("/api/v1/analyze", {"X-API-Key": "syxp_a"}))
    b = rate_limit_key(_request("/api/v1/analyze", {"X-API-Key": "syxp_b"}))
    assert a != b and a.startswith("cred:") and "syxp_a" not in a
    assert a == rate_limit_key(_request("/api/v1/runs", {"X-API-Key": "syxp_a"}))
    bearer = rate_limit_key(_request("/mcp", {"Authorization": "Bearer tok"}))
    assert bearer.startswith("cred:")


def test_other_requests_are_limited_per_address():
    assert rate_limit_key(_request("/api/upload", {"Authorization": "Bearer tok"})) == "10.0.0.9"
    assert (
        rate_limit_key(_request("/api/upload", {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}))
        == "1.2.3.4"
    )
    # No credential on a programmatic path: the address
    assert rate_limit_key(_request("/api/v1/models", {})) == "10.0.0.9"


# ---------------------------------------------------------------------------
# API keys of accounts whose access changes
# ---------------------------------------------------------------------------


def test_busy_api_key_still_refreshes_its_roles(monkeypatch):
    from datetime import datetime
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from backend.services import api_key_service
    from backend.services.api_key_service import ApiKeyService

    clock = SimpleNamespace(now=1000.0)
    lookups = []
    monkeypatch.setattr(api_key_service.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(api_key_service, "_roles_refreshed_at", {})
    monkeypatch.setattr(
        api_key_service, "get_keycloak_admin_token", lambda: lookups.append(clock.now)
    )
    key = SimpleNamespace(
        id="k1", user_id=SUB, user_email="a@b.hu", user_roles=["r"], last_used_at=None
    )
    repo = MagicMock()
    repo.get_active_by_key_hash.return_value = key
    repo.update_last_used.side_effect = lambda k: setattr(k, "last_used_at", datetime.utcnow())
    service = ApiKeyService(repo)

    # Used every minute for ten minutes: checked at the start and again after the TTL
    for _ in range(10):
        service.authenticate_by_api_key("syxp_x")
        clock.now += 60
    assert lookups == [1000.0, 1300.0]
    # The last-use time is written once, not on every request within the minute
    assert repo.update_last_used.call_count == 1


def test_mcp_and_api_are_proxied_by_nginx():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for name in ("nginx.conf", "nginx.ssl.conf"):
        conf = (root / "frontend" / name).read_text()
        assert "location = /mcp {" in conf, name


def test_api_key_may_come_as_the_bearer_token(monkeypatch):
    seen = []
    monkeypatch.setattr(security, "_authenticate_api_key", lambda key: seen.append(("key", key)))
    monkeypatch.setattr(
        security, "_authenticate_jwt", lambda c, s: seen.append(("jwt", c.credentials))
    )

    security.authenticate_credentials(None, "syxp_abc")  # clients that only set Authorization
    security.authenticate_credentials(None, "eyJ.a.b")  # a Keycloak access token
    security.authenticate_credentials("syxp_x", "eyJ.a.b")  # the API key wins
    assert seen == [("key", "syxp_abc"), ("jwt", "eyJ.a.b"), ("key", "syxp_x")]
    with pytest.raises(HTTPException) as e:
        security.authenticate_credentials(None, None)
    assert e.value.status_code == 401
