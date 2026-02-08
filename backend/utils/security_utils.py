"""
Security utilities for the backend.

Provides functions for safe output encoding and input sanitization.
OWASP: A03:2021 - Injection Prevention
"""

import re
import shlex
from urllib.parse import quote, urlparse


def safe_content_disposition(filename: str) -> str:
    """
    Create a safe Content-Disposition header value (RFC 5987).

    Prevents HTTP header injection attacks by properly encoding the filename.
    Removes path components, control characters, and encodes special characters.

    Args:
        filename: The original filename

    Returns:
        Safe Content-Disposition header value

    Example:
        >>> safe_content_disposition("report.csv")
        "attachment; filename*=UTF-8''report.csv"
        >>> safe_content_disposition("../../etc/passwd")
        "attachment; filename*=UTF-8''passwd"
    """
    if not filename:
        filename = "download"

    # Remove any path components (prevent path traversal in header)
    filename = filename.split("/")[-1].split("\\")[-1]

    # Remove control characters, newlines, and carriage returns
    # These could be used for HTTP response splitting attacks
    filename = re.sub(r"[\x00-\x1f\x7f\r\n]", "", filename)

    # Limit length to prevent buffer issues
    if len(filename) > 200:
        # Preserve extension if possible
        if "." in filename:
            name, ext = filename.rsplit(".", 1)
            max_name_len = 200 - len(ext) - 1
            filename = f"{name[:max_name_len]}.{ext}"
        else:
            filename = filename[:200]

    # Ensure filename is not empty after sanitization
    if not filename:
        filename = "download"

    # RFC 5987 encoding for non-ASCII and special characters
    # This properly handles Unicode filenames and special characters
    filename_encoded = quote(filename, safe="")

    return f"attachment; filename*=UTF-8''{filename_encoded}"


# ============================================================================
# Shell Injection Prevention (OWASP: A03:2021)
# ============================================================================


def shell_escape(value: str) -> str:
    """
    Escape a string for safe shell interpolation.

    Uses shlex.quote to properly escape special characters that could
    lead to command injection in bash scripts.

    Args:
        value: The string to escape

    Returns:
        Shell-safe escaped string

    Example:
        >>> shell_escape('hello; rm -rf /')
        "'hello; rm -rf /'"
        >>> shell_escape('$(whoami)')
        "'$(whoami)'"
    """
    return shlex.quote(value)


def validate_slurm_identifier(value: str, field_name: str) -> str:
    """
    Validate Slurm job identifiers.

    Ensures the value contains only safe characters for Slurm job names
    and identifiers (alphanumeric, hyphen, underscore).

    Args:
        value: The identifier value to validate
        field_name: Name of the field for error messages

    Returns:
        The validated value (unchanged if valid)

    Raises:
        ValueError: If the value contains invalid characters
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise ValueError(f"{field_name} contains invalid characters")
    return value


def validate_url(value: str, field_name: str) -> str:
    """
    Validate URL uses http or https scheme.

    Prevents injection of malicious URL schemes that could be exploited
    in shell contexts (e.g., file://, data://).

    Args:
        value: The URL to validate
        field_name: Name of the field for error messages

    Returns:
        The validated URL (unchanged if valid)

    Raises:
        ValueError: If the URL doesn't use http or https scheme
    """
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{field_name} must use http or https")
    return value
