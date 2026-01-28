"""
Permission endpoints router.

Provides endpoints for checking user permissions and validating API keys.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_permission_service
from backend.core.security import User, get_current_user
from backend.services.permission_service import PermissionService
from backend.schemas.requests import ValidateKeysRequest
from backend.schemas.responses import PermissionResponse, ValidateKeysResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Permissions"])


@router.get(
    "/permissions/me",
    response_model=PermissionResponse
)
def get_my_permissions(
    current_user: User = Depends(get_current_user),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Get current user's permissions.

    Returns:
        PermissionResponse with use_hunren_keys and is_admin flags
    """
    return permission_service.get_my_permissions(
        user_id=current_user.user_id,
        email=current_user.email
    )


@router.post(
    "/validate-keys",
    response_model=ValidateKeysResponse
)
async def validate_api_keys(
    request: ValidateKeysRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Validate OpenAI API key before analysis.

    This endpoint verifies the API key is valid without storing it.

    Returns:
        ValidateKeysResponse with valid flag

    Raises:
        HTTPException: If the API key is invalid
    """
    try:
        import openai
        client = openai.OpenAI(api_key=request.openai_api_key)
        # Make a minimal API call to verify the key
        client.models.list()
        return ValidateKeysResponse(valid=True)
    except openai.AuthenticationError as e:
        logger.warning(f"Invalid API key provided by user {current_user.user_id}")
        raise HTTPException(
            status_code=400,
            detail="Invalid API key. Please check your key and try again."
        )
    except openai.RateLimitError as e:
        logger.warning(f"Rate limited API key for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=400,
            detail="API key rate limited. Your OpenAI account may have insufficient credits."
        )
    except Exception as e:
        logger.error(f"API key validation failed for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"API key validation failed: {str(e)}"
        )
