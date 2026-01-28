"""
Permission service for managing user API key access.

Encapsulates business logic for checking and granting permissions.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from backend.core.config import get_settings
from backend.repositories.permission_repository import PermissionRepository
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)


@dataclass
class UserWithPermission:
    """User data with permission info for admin listing."""
    user_id: str
    use_hunren_keys: bool
    granted_by: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class PermissionService:
    """
    Service for user permission operations.

    Handles permission checks and admin management of user access.
    """

    def __init__(self, permission_repo: PermissionRepository):
        self.permission_repo = permission_repo
        self.settings = get_settings()

    def has_hunren_access(self, user_id: str, email: Optional[str] = None) -> bool:
        """
        Check if a user has HUN-REN API key access.

        Admins (defined in ADMIN_EMAILS) automatically have access.
        Regular users need explicit database permission.

        Args:
            user_id: The user's UUID as string
            email: The user's email (optional, used for admin check)

        Returns:
            True if user has permission, False otherwise
        """
        # Admins automatically have HUN-REN access
        if email and self.is_admin(email):
            return True

        user_uuid = parse_uuid(user_id)
        return self.permission_repo.has_hunren_access(user_uuid)

    def is_admin(self, email: str) -> bool:
        """
        Check if a user is an admin.

        Args:
            email: The user's email address

        Returns:
            True if user is admin, False otherwise
        """
        return self.settings.admin.is_admin(email)

    def get_my_permissions(self, user_id: str, email: str) -> dict:
        """
        Get current user's permission info.

        Admins (defined in ADMIN_EMAILS) automatically have HUN-REN access.
        Regular users need explicit database permission.

        Args:
            user_id: The user's UUID as string
            email: The user's email address

        Returns:
            Dictionary with permission flags
        """
        is_admin = self.is_admin(email) if email else False

        # Admins automatically have HUN-REN access
        if is_admin:
            use_hunren_keys = True
        else:
            use_hunren_keys = self.has_hunren_access(user_id)

        return {
            "use_hunren_keys": use_hunren_keys,
            "is_admin": is_admin
        }

    def set_permission(
        self,
        user_id: str,
        use_hunren_keys: bool,
        granted_by: str
    ) -> None:
        """
        Grant or revoke HUN-REN key permission for a user.

        Args:
            user_id: The target user's UUID as string
            use_hunren_keys: Whether to grant or revoke access
            granted_by: Email of admin making the change
        """
        user_uuid = parse_uuid(user_id)
        self.permission_repo.set_permission(
            user_id=user_uuid,
            use_hunren_keys=use_hunren_keys,
            granted_by=granted_by
        )
        action = "granted" if use_hunren_keys else "revoked"
        logger.info(f"HUN-REN key access {action} for user {user_id} by {granted_by}")

    def list_users_with_permissions(self) -> List[dict]:
        """
        Get all users with their permission status.

        Fetches users from Supabase Admin API and joins with local permissions.

        Returns:
            List of users with permission info (includes email)
        """
        import httpx

        # Get permissions from local database
        permissions = self.permission_repo.get_all_permissions_dict()

        # Fetch users from Supabase Admin API
        supabase_url = self.settings.auth.supabase_url
        service_role_key = self.settings.auth.supabase_service_role_key

        if not supabase_url or not service_role_key:
            logger.debug("Supabase service role key not configured, returning only users with permissions")
            # Fallback: return only users who have permission records
            all_permissions = self.permission_repo.get_all_permissions()
            return [
                {
                    "user_id": str(p.user_id),
                    "email": f"User {str(p.user_id)[:8]}...",
                    "user_created_at": p.created_at,
                    "use_hunren_keys": p.use_hunren_keys,
                    "granted_by": p.granted_by,
                    "permission_updated_at": p.updated_at,
                }
                for p in all_permissions
            ]

        try:
            # Supabase Admin API to list users
            response = httpx.get(
                f"{supabase_url}/auth/v1/admin/users",
                headers={
                    "apikey": service_role_key,
                    "Authorization": f"Bearer {service_role_key}",
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            users = data.get("users", [])

            # Merge with permissions
            result = []
            for user in users:
                user_id = user.get("id")
                perm = permissions.get(user_id, {})
                result.append({
                    "user_id": user_id,
                    "email": user.get("email", ""),
                    "user_created_at": user.get("created_at"),
                    "use_hunren_keys": perm.get("use_hunren_keys", False),
                    "granted_by": perm.get("granted_by"),
                    "permission_updated_at": perm.get("permission_updated_at"),
                })

            return result

        except Exception as e:
            logger.error(f"Failed to fetch users from Supabase: {e}")
            # Fallback: return only users who have permission records
            all_permissions = self.permission_repo.get_all_permissions()
            return [
                {
                    "user_id": str(p.user_id),
                    "email": f"User {str(p.user_id)[:8]}...",
                    "user_created_at": p.created_at,
                    "use_hunren_keys": p.use_hunren_keys,
                    "granted_by": p.granted_by,
                    "permission_updated_at": p.updated_at,
                }
                for p in all_permissions
            ]

    def delete_user_permissions(self, user_id: str) -> bool:
        """
        Delete a user's permission record (for GDPR deletion).

        Args:
            user_id: The user's UUID as string

        Returns:
            True if deleted, False if not found
        """
        user_uuid = parse_uuid(user_id)
        return self.permission_repo.delete_by_user_id(user_uuid)
