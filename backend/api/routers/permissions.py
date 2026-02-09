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


def validate_api_key_format(api_key: str) -> tuple[bool, str]:
    """
    Validate OpenAI API key format before making external API call.

    This prevents wasting API calls on obviously invalid keys and
    provides faster feedback to users.

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
    return permission_service.get_my_permissions(
        user_id=current_user.user_id, email=current_user.email
    )


@router.post("/validate-keys", response_model=ValidateKeysResponse)
@limiter.limit("20/minute")
async def validate_api_keys(
    request: Request, body: ValidateKeysRequest, current_user: User = Depends(get_current_user)
):
    """
    Validate OpenAI API key before analysis.

    This endpoint verifies the API key is valid without storing it.
    First checks format locally, then makes an API call to verify.

    Returns:
        ValidateKeysResponse with valid flag

    Raises:
        HTTPException: If the API key is invalid
    """
    # Validate format before making external API call
    is_valid_format, format_error = validate_api_key_format(body.openai_api_key)
    if not is_valid_format:
        logger.warning(f"Invalid API key format from user {current_user.user_id}")
        raise HTTPException(status_code=400, detail=format_error)

    try:
        import openai

        client = openai.OpenAI(api_key=body.openai_api_key)
        # Make a minimal API call to verify the key
        client.models.list()
        return ValidateKeysResponse(valid=True)
    except openai.AuthenticationError:
        logger.warning(f"Invalid API key provided by user {current_user.user_id}")
        raise HTTPException(
            status_code=400, detail="Invalid API key. Please check your key and try again."
        )
    except openai.RateLimitError:
        logger.warning(f"Rate limited API key for user {current_user.user_id}")
        raise HTTPException(
            status_code=400,
            detail="API key rate limited. Your OpenAI account may have insufficient credits.",
        )
    except Exception:
        logger.warning(f"API key validation failed for user {current_user.user_id}")
        raise HTTPException(
            status_code=400, detail="API key validation failed. Please check your key."
        )
