"""
Common validation utilities.
"""

import re
from typing import Any
from uuid import UUID

from backend.core.exceptions import ValidationError

# OpenAI API key format pattern
# Keys start with "sk-" followed by alphanumeric chars, hyphens, and underscores
# Minimum 32 characters after prefix (typical keys are 48-51 chars total)
OPENAI_KEY_PATTERN = re.compile(r"^sk-[a-zA-Z0-9_-]{32,}$")

# Google Gemini API key format pattern
# Keys start with "AIza" followed by alphanumeric chars, hyphens, and underscores
GEMINI_KEY_PATTERN = re.compile(r"^AIza[a-zA-Z0-9_-]{35,}$")


def validate_openai_key_format(api_key: str) -> tuple[bool, str]:
    """
    Validate OpenAI API key format before making external API call.

    Args:
        api_key: The API key to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key is required"

    if not OPENAI_KEY_PATTERN.match(api_key):
        return False, "Invalid API key format. OpenAI keys start with 'sk-'"

    return True, ""


def validate_gemini_key_format(api_key: str) -> tuple[bool, str]:
    """
    Validate Google Gemini API key format (format check only, no live API call).

    Args:
        api_key: The API key to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key is required"

    if not GEMINI_KEY_PATTERN.match(api_key):
        return False, "Invalid API key format. Gemini keys start with 'AIza'"

    return True, ""


def parse_uuid(value: Any, field_name: str = "id") -> UUID:
    """
    Safely parse a string (or UUID) to a UUID object.

    Args:
        value: string or UUID to parse
        field_name: Name of the field for error reporting

    Returns:
        UUID object

    Raises:
        ValidationError: If the value is not a valid UUID
    """
    if isinstance(value, UUID):
        return value

    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(
            f"Invalid {field_name} format: '{value}' is not a valid UUID",
            field=field_name,
            value=str(value),
        )
