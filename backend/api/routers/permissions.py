"""
Permission endpoints router.

Provides endpoints for checking user permissions and validating API keys.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import get_permission_service
from backend.core.rate_limit import limiter
from backend.core.security import User, get_current_user
from backend.schemas.requests import ValidateKeysRequest
from backend.schemas.responses import PermissionResponse, ValidateKeysResponse
from backend.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

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


router = APIRouter(prefix="/api", tags=["Permissions"])


@router.get("/permissions/me", response_model=PermissionResponse)
@limiter.limit("60/minute")
def get_my_permissions(
    request: Request,
    current_user: User = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Get current user's permissions.

    Returns:
        PermissionResponse with use_hunren_keys and is_admin flags
    """
    return permission_service.get_my_permissions(user=current_user)


@router.post("/validate-keys", response_model=ValidateKeysResponse)
@limiter.limit("20/minute")
async def validate_api_keys(
    request: Request, body: ValidateKeysRequest, current_user: User = Depends(get_current_user)
):
    """
    Validate API keys before analysis.

    Validates whichever key(s) are provided:
    - Gemini key: format check only (no live API call)
    - OpenAI key: format check + live API call

    At least one key must be provided.

    Returns:
        ValidateKeysResponse with valid flag

    Raises:
        HTTPException: If validation fails
    """
    if not body.gemini_api_key and not body.openai_api_key:
        raise HTTPException(status_code=400, detail="At least one API key must be provided")

    # Validate Gemini key format if provided
    if body.gemini_api_key:
        is_valid_format, format_error = validate_gemini_key_format(body.gemini_api_key)
        if not is_valid_format:
            logger.warning(f"Invalid Gemini API key format from user {current_user.user_id}")
            raise HTTPException(status_code=400, detail=format_error)

    # Validate OpenAI key if provided (format + live check)
    if body.openai_api_key:
        is_valid_format, format_error = validate_openai_key_format(body.openai_api_key)
        if not is_valid_format:
            logger.warning(f"Invalid OpenAI API key format from user {current_user.user_id}")
            raise HTTPException(status_code=400, detail=format_error)

        try:
            import openai

            client = openai.OpenAI(api_key=body.openai_api_key)
            # Make a minimal API call to verify the key
            client.models.list()
        except openai.AuthenticationError:
            logger.warning(f"Invalid OpenAI API key provided by user {current_user.user_id}")
            raise HTTPException(
                status_code=400,
                detail="Invalid OpenAI API key. Please check your key and try again.",
            )
        except openai.RateLimitError:
            logger.warning(f"Rate limited OpenAI API key for user {current_user.user_id}")
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key rate limited. Your account may have insufficient credits.",
            )
        except Exception:
            logger.warning(f"OpenAI API key validation failed for user {current_user.user_id}")
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key validation failed. Please check your key.",
            )

    return ValidateKeysResponse(valid=True)
