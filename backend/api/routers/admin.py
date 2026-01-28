"""
Admin endpoints router.

Provides endpoints for administrative user management.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import get_permission_service
from backend.core.rate_limit import limiter
from backend.core.config import get_settings
from backend.core.security import User, get_current_user
from backend.services.permission_service import PermissionService
from backend.schemas.requests import UpdatePermissionRequest
from backend.schemas.responses import (
    UsersWithPermissionsResponse,
    UserPermissionInfo,
    UpdatePermissionResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency that requires admin access.

    Raises:
        HTTPException: If user is not an admin
    """
    settings = get_settings()
    if not settings.admin.is_admin(current_user.email):
        logger.warning(f"Non-admin user {current_user.email} attempted admin access")
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get(
    "/users",
    response_model=UsersWithPermissionsResponse
)
@limiter.limit("30/minute")
def list_users_with_permissions(
    request: Request,
    admin: User = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    List all users with their permissions.

    Returns:
        UsersWithPermissionsResponse with list of users and their permission status
    """
    users = permission_service.list_users_with_permissions()
    return UsersWithPermissionsResponse(
        users=[
            UserPermissionInfo(
                user_id=u["user_id"],
                email=u["email"],
                use_hunren_keys=u["use_hunren_keys"],
                granted_by=u["granted_by"],
                user_created_at=u["user_created_at"],
                permission_updated_at=u["permission_updated_at"]
            )
            for u in users
        ]
    )


@router.put(
    "/users/{user_id}/permissions",
    response_model=UpdatePermissionResponse
)
@limiter.limit("20/minute")
def update_user_permission(
    request: Request,
    user_id: str,
    body: UpdatePermissionRequest,
    admin: User = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Grant or revoke HUN-REN key permission for a user.

    Args:
        user_id: The target user's UUID
        request: Permission update request

    Returns:
        UpdatePermissionResponse with success status
    """
    # Validate UUID format to prevent injection
    from backend.utils import parse_uuid
    try:
        parse_uuid(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    permission_service.set_permission(
        user_id=user_id,
        use_hunren_keys=body.use_hunren_keys,
        granted_by=admin.email
    )

    action = "granted" if body.use_hunren_keys else "revoked"
    logger.info(f"Admin {admin.email} {action} HUN-REN access for user {user_id}")

    return UpdatePermissionResponse(
        success=True,
        user_id=user_id,
        use_hunren_keys=body.use_hunren_keys
    )
