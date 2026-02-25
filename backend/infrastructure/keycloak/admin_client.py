"""
Shared Keycloak admin token management with caching.

Provides a cached admin token helper to avoid redundant token requests
across services that need Keycloak Admin API access.
"""

import logging
import time

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

_admin_token_cache: dict = {"token": None, "expires_at": 0.0}


def get_keycloak_admin_token() -> str | None:
    """
    Obtain a Keycloak admin access token, returning a cached token if still valid.

    Caches the token with a 30-second safety margin before expiry.

    Returns:
        Admin access token string, or None on failure.
    """
    now = time.monotonic()

    # Return cached token if still valid (with 30s safety margin)
    cached = _admin_token_cache
    if cached["token"] and now < cached["expires_at"] - 30:
        return cached["token"]

    settings = get_settings()
    token_url = settings.auth.token_url
    username = settings.auth.keycloak_admin_username
    password = settings.auth.keycloak_admin_password

    if not username or not password:
        logger.debug("Keycloak admin credentials not configured")
        return None

    try:
        response = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": username,
                "password": password,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token")
        expires_in = data.get("expires_in", 60)

        # Cache the token
        _admin_token_cache["token"] = token
        _admin_token_cache["expires_at"] = now + expires_in

        return token
    except Exception as e:
        logger.error(f"Failed to obtain Keycloak admin token: {e}")
        return None
