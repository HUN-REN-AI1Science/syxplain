"""
Repository for user permission data access.

Handles CRUD operations for UserPermission entities.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.infrastructure.database.models import UserPermission
from backend.repositories.base import BaseRepository


class PermissionRepository(BaseRepository[UserPermission]):
    """
    Repository for managing user permissions.

    Provides methods for checking and managing user API key access permissions.
    """

    def __init__(self, db: Session):
        """Initialize with UserPermission model."""
        super().__init__(UserPermission, db)

    def get_by_user_id(self, user_id: UUID) -> UserPermission | None:
        """
        Get permission record for a specific user.

        Args:
            user_id: The user's UUID

        Returns:
            UserPermission if found, None otherwise
        """
        return self.db.query(UserPermission).filter(UserPermission.user_id == user_id).first()

    def has_hunren_access(self, user_id: UUID) -> bool:
        """
        Check if a user has HUN-REN API key access.

        Args:
            user_id: The user's UUID

        Returns:
            True if user has permission, False otherwise
        """
        permission = self.get_by_user_id(user_id)
        return permission is not None and permission.use_hunren_keys

    def set_permission(
        self, user_id: UUID, use_hunren_keys: bool, granted_by: str | None = None
    ) -> UserPermission:
        """
        Set or update a user's permission.

        Creates a new permission record if one doesn't exist,
        or updates the existing record.

        Args:
            user_id: The user's UUID
            use_hunren_keys: Whether user can use HUN-REN keys
            granted_by: Email of admin who granted/changed permission

        Returns:
            The created or updated UserPermission
        """
        permission = self.get_by_user_id(user_id)

        if permission:
            permission.use_hunren_keys = use_hunren_keys
            permission.updated_at = datetime.utcnow()
            permission.granted_by = granted_by
            self.db.commit()
            self.db.refresh(permission)
        else:
            permission = UserPermission(
                user_id=user_id, use_hunren_keys=use_hunren_keys, granted_by=granted_by
            )
            permission = self.create(permission)

        return permission

    def get_all_permissions(self) -> list[UserPermission]:
        """
        Get all user permissions.

        Returns:
            List of all UserPermission records
        """
        return self.db.query(UserPermission).all()

    def get_all_permissions_dict(self) -> dict:
        """
        Get all permissions as a dict keyed by user_id.

        Returns:
            Dict mapping user_id to permission record
        """
        permissions = self.get_all_permissions()
        return {
            str(p.user_id): {
                "use_hunren_keys": p.use_hunren_keys,
                "granted_by": p.granted_by,
                "permission_updated_at": p.updated_at,
            }
            for p in permissions
        }

    def delete_by_user_id(self, user_id: UUID) -> bool:
        """
        Delete a user's permission record.

        Args:
            user_id: The user's UUID

        Returns:
            True if deleted, False if not found
        """
        permission = self.get_by_user_id(user_id)
        if permission:
            self.db.delete(permission)
            self.db.commit()
            return True
        return False
