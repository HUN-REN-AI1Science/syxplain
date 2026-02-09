"""
Rate limiting configuration.

Provides a shared limiter instance for use across routers.
"""

from starlette.requests import Request

from slowapi import Limiter


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


# Rate limiter instance (used by routers for endpoint-specific limits)
# Default: 200 requests per minute per real client IP
limiter = Limiter(key_func=_get_real_client_ip, default_limits=["200/minute"])
