"""
Rate limiting configuration.

Provides a shared limiter instance for use across routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter instance (used by routers for endpoint-specific limits)
# Default: 100 requests per minute per IP address
# This provides reasonable protection against API abuse while allowing normal usage
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
