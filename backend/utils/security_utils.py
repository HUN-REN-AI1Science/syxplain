"""
Security utilities for the backend.

Provides functions for safe output encoding and input sanitization.
OWASP: A03:2021 - Injection Prevention
"""
import re
from urllib.parse import quote


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
    filename = re.sub(r'[\x00-\x1f\x7f\r\n]', '', filename)

    # Limit length to prevent buffer issues
    if len(filename) > 200:
        # Preserve extension if possible
        if '.' in filename:
            name, ext = filename.rsplit('.', 1)
            max_name_len = 200 - len(ext) - 1
            filename = f"{name[:max_name_len]}.{ext}"
        else:
            filename = filename[:200]

    # Ensure filename is not empty after sanitization
    if not filename:
        filename = "download"

    # RFC 5987 encoding for non-ASCII and special characters
    # This properly handles Unicode filenames and special characters
    filename_encoded = quote(filename, safe='')

    return f"attachment; filename*=UTF-8''{filename_encoded}"


def sanitize_error_message(message: str, max_length: int = 200) -> str:
    """
    Sanitize error messages before returning to clients.

    Removes potentially sensitive information like file paths,
    stack traces, and internal implementation details.

    Args:
        message: The original error message
        max_length: Maximum length of returned message

    Returns:
        Sanitized error message safe for client display
    """
    if not message:
        return "An error occurred"

    # Remove file paths (Unix and Windows)
    message = re.sub(r'(/[a-zA-Z0-9_\-./]+)+', '[path]', message)
    message = re.sub(r'([A-Za-z]:\\[a-zA-Z0-9_\-\\./]+)+', '[path]', message)

    # Remove potential stack trace lines
    message = re.sub(r'File ".*?", line \d+', '[location]', message)
    message = re.sub(r'at .*?:\d+:\d+', '[location]', message)

    # Remove IP addresses
    message = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[ip]', message)

    # Truncate to max length
    if len(message) > max_length:
        message = message[:max_length] + "..."

    return message
