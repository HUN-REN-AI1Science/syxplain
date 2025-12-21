"""
Common validation utilities.
"""
from typing import Any
from uuid import UUID

from backend.core.exceptions import ValidationError


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
            value=str(value)
        )
