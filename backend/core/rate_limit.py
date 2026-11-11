"""
Rate limiting configuration.

Provides a shared limiter instance for use across routers.
"""

import hashlib

from slowapi import Limiter
from starlette.requests import Request

# Paths used by scripts and technical clients: many callers can share one address
# (a chat platform, a campus proxy), so these are limited per credential.
CREDENTIAL_KEYED_PREFIXES = ("/api/v1", "/mcp")


def _get_real_client_ip(request: Request) -> str:
    """
    Extract the real client IP from behind a reverse proxy.

    Reads X-Forwarded-For header set by nginx, falling back to
    the direct connection address if the header is absent.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For: client, proxy1, proxy2 — first entry is the real client
        return forwarded_for.split(",")[0].strip()
    return request.client.host


def rate_limit_key(request: Request) -> str:
    """
    The bucket a request is counted in: the presented credential on the programmatic
    API and the MCP endpoint, the client IP everywhere else.
    """
    if request.url.path.startswith(CREDENTIAL_KEYED_PREFIXES):
        credential = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        if credential:
            return "cred:" + hashlib.sha256(credential.encode()).hexdigest()[:24]
    return _get_real_client_ip(request)


# Rate limiter instance (used by routers for endpoint-specific limits)
# Default: 200 requests per minute per key
limiter = Limiter(key_func=rate_limit_key, default_limits=["200/minute"])
