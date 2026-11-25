"""
Checks for user-supplied URLs the backend will send requests to (SSRF protection).
"""

import ipaddress
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import SplitResult, urlsplit


class UnsafeUrlError(ValueError):
    """The URL is malformed or points at an address the backend must not call."""


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # An IPv4-mapped IPv6 address (::ffff:10.0.0.1) is judged by its IPv4 part
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    # Loopback, private (10/8, 172.16/12, 192.168/16, fc00::/7), link-local and cloud
    # metadata (169.254/16, fe80::/10), shared (100.64/10), unspecified and reserved
    # ranges are all non-global; multicast is never an HTTP server
    return not ip.is_global or ip.is_multicast


def parse_http_url(url: str) -> SplitResult:
    """
    Split an http(s) URL that has a host.

    Raises:
        UnsafeUrlError: (a ValueError) With a message that can be shown to the user.
    """
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        raise UnsafeUrlError("The base URL is not a valid URL.")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrlError("The base URL must start with http:// or https://")
    return parts


def ensure_public_http_url(
    url: str, resolve: Callable[..., list[Any]] = socket.getaddrinfo
) -> None:
    """
    Reject a URL unless it is http(s) and every address its host resolves to is public.

    The check runs before any request to the URL. The HTTP client resolves the host
    again, so a DNS answer that changes in between is not caught.

    Args:
        url: The URL to check.
        resolve: Name resolver with the socket.getaddrinfo signature (injectable for tests).

    Raises:
        UnsafeUrlError: With a message that can be shown to the user.
    """
    parts = parse_http_url(url)
    host = parts.hostname
    try:
        infos = resolve(host, parts.port or (443 if parts.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError, OSError):
        raise UnsafeUrlError(f"Could not resolve the host '{host}' in the base URL.")
    if not infos:
        raise UnsafeUrlError(f"Could not resolve the host '{host}' in the base URL.")

    for info in infos:
        # sockaddr is (address, port) for IPv4 and (address, port, flow, scope) for IPv6;
        # drop any %scope suffix of a link-local IPv6 address before parsing
        address = str(info[4][0]).split("%", 1)[0]
        if _is_blocked(ipaddress.ip_address(address)):
            raise UnsafeUrlError(
                "The base URL points to a private, local or reserved network address, "
                "which is not allowed. Use a publicly reachable endpoint."
            )
