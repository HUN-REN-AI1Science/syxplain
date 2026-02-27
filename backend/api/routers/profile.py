"""
Profile endpoints router.

Provides endpoints for user profile management including
profile data retrieval and GDPR-compliant account deletion.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_profile_service
from backend.core.exceptions import ExternalServiceError
from backend.core.security import User, get_current_user_jwt_only
from backend.schemas.responses import ProfileDeleteResponse, ProfileResponse
from backend.services.profile_service import ProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Profile"])


@router.get("/profile", response_model=ProfileResponse)
def get_profile(
    current_user: User = Depends(get_current_user_jwt_only),
    profile_service: ProfileService = Depends(get_profile_service),
):
    """
    Returns user profile data.

    Returns:
        ProfileResponse with email, creation date, and usage stats
    """
    return profile_service.get_profile(user_id=current_user.user_id, email=current_user.email)


@router.delete("/profile", response_model=ProfileDeleteResponse)
async def delete_profile(
    current_user: User = Depends(get_current_user_jwt_only),
    profile_service: ProfileService = Depends(get_profile_service),
):
    """
    GDPR-compliant account deletion.

    Removes all user data from the database and
    deletes the user from Keycloak.

    Returns:
        ProfileDeleteResponse with success message

    Raises:
        HTTPException: If deletion fails
    """
    try:
        await profile_service.delete_account(current_user.user_id)
        return ProfileDeleteResponse()
    except ExternalServiceError as e:
        logger.error(f"Failed to delete account for user {current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e.message))
    except Exception as e:
        logger.error(f"Failed to delete account for user {current_user.user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {e!s}")
