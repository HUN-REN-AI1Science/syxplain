"""
Security event logging.

Provides logging for security-relevant events including:
- Failed authentication attempts
- Rate limit violations
- Suspicious activity patterns

OWASP: A09:2021 - Security Logging and Monitoring Failures
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Separate logger for security events (can be routed to dedicated log file)
security_logger = logging.getLogger("security")


class SecurityLogger:
    """
    Security event logger with failed auth tracking.

    Tracks failed authentication attempts per IP and logs alerts
    when thresholds are exceeded.
    """

    # Alert threshold: 5 failed attempts within 15 minutes
    FAILED_AUTH_THRESHOLD = 5
    FAILED_AUTH_WINDOW_MINUTES = 15

    def __init__(self):
        # Track failed auth attempts: {ip: [timestamp1, timestamp2, ...]}
        self._failed_auths: dict[str, list[datetime]] = defaultdict(list)

    def _cleanup_old_attempts(self, ip: str) -> None:
        """Remove attempts older than the tracking window."""
        cutoff = datetime.utcnow() - timedelta(minutes=self.FAILED_AUTH_WINDOW_MINUTES)
        self._failed_auths[ip] = [
            ts for ts in self._failed_auths[ip] if ts > cutoff
        ]

    def log_failed_auth(
        self,
        ip: str,
        endpoint: str,
        reason: str,
        user_id: Optional[str] = None
    ) -> None:
        """
        Log a failed authentication attempt.

        Tracks attempts per IP and logs an alert if threshold is exceeded.

        Args:
            ip: Client IP address
            endpoint: The endpoint that was accessed
            reason: Reason for authentication failure
            user_id: User ID if known (e.g., from invalid token)
        """
        self._cleanup_old_attempts(ip)
        self._failed_auths[ip].append(datetime.utcnow())

        attempt_count = len(self._failed_auths[ip])

        security_logger.warning(
            f"Failed auth attempt | ip={ip} | endpoint={endpoint} | "
            f"reason={reason} | user_id={user_id or 'unknown'} | "
            f"attempts_in_window={attempt_count}"
        )

        # Check if threshold exceeded
        if attempt_count >= self.FAILED_AUTH_THRESHOLD:
            security_logger.error(
                f"ALERT: Multiple failed auth attempts | ip={ip} | "
                f"count={attempt_count} | window={self.FAILED_AUTH_WINDOW_MINUTES}min | "
                f"endpoint={endpoint}"
            )

    def log_rate_limit_exceeded(
        self,
        ip: str,
        endpoint: str,
        limit: str
    ) -> None:
        """
        Log a rate limit violation.

        Args:
            ip: Client IP address
            endpoint: The endpoint that was rate limited
            limit: The rate limit that was exceeded
        """
        security_logger.warning(
            f"Rate limit exceeded | ip={ip} | endpoint={endpoint} | limit={limit}"
        )

    def log_suspicious_activity(
        self,
        ip: str,
        activity_type: str,
        details: str
    ) -> None:
        """
        Log suspicious activity.

        Args:
            ip: Client IP address
            activity_type: Type of suspicious activity
            details: Additional details
        """
        security_logger.warning(
            f"Suspicious activity | ip={ip} | type={activity_type} | details={details}"
        )


# Global security logger instance
_security_logger: Optional[SecurityLogger] = None


def get_security_logger() -> SecurityLogger:
    """Get the global security logger instance."""
    global _security_logger
    if _security_logger is None:
        _security_logger = SecurityLogger()
    return _security_logger


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling proxies.

    Args:
        request: The FastAPI request

    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (set by reverse proxies)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return "unknown"


class SecurityLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs security-relevant HTTP responses.

    Logs 401 (Unauthorized) and 403 (Forbidden) responses to help
    detect potential attacks and misconfigurations.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Log authentication/authorization failures
        if response.status_code in (401, 403):
            sec_logger = get_security_logger()
            ip = get_client_ip(request)
            endpoint = f"{request.method} {request.url.path}"

            if response.status_code == 401:
                sec_logger.log_failed_auth(
                    ip=ip,
                    endpoint=endpoint,
                    reason="unauthorized_response"
                )
            else:
                security_logger.warning(
                    f"Access denied | ip={ip} | endpoint={endpoint} | status=403"
                )

        # Log rate limit responses (429)
        if response.status_code == 429:
            sec_logger = get_security_logger()
            ip = get_client_ip(request)
            endpoint = f"{request.method} {request.url.path}"

            sec_logger.log_rate_limit_exceeded(
                ip=ip,
                endpoint=endpoint,
                limit=response.headers.get("X-RateLimit-Limit", "unknown")
            )

        return response
