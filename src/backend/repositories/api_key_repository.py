"""
Repository for API key data access.

Provides CRUD operations and lookup by key hash for authentication.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.infrastructure.database.models import ApiKey
from backend.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    """Repository for API key operations."""

    def __init__(self, db: Session):
        super().__init__(ApiKey, db)

    def get_active_by_key_hash(self, key_hash: str) -> ApiKey | None:
        """Look up an active, non-expired API key by its SHA-256 hash."""
        key = (
            self.db.query(ApiKey)
            .filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
            .first()
        )
        if key and key.is_expired:
            return None
        return key

    def get_active_for_user(self, user_id: UUID) -> ApiKey | None:
        """Get the single active API key for a user, if any."""
        return (
            self.db.query(ApiKey)
            .filter(ApiKey.user_id == user_id, ApiKey.is_active.is_(True))
            .first()
        )

    def update_last_used(self, key: ApiKey) -> None:
        """Update the last_used_at timestamp."""
        key.last_used_at = datetime.utcnow()
        self.db.commit()

    def update_roles(self, key: ApiKey, roles: list[str]) -> None:
        """Update the cached roles on an API key."""
        key.user_roles = roles
        self.db.commit()

    def deactivate(self, key: ApiKey) -> None:
        """Soft-delete by setting is_active to False."""
        key.is_active = False
        self.db.commit()

    def delete_all_for_user(self, user_id: UUID) -> int:
        """Delete all API keys for a user (GDPR). Returns count deleted."""
        count = self.db.query(ApiKey).filter(ApiKey.user_id == user_id).delete()
        self.db.commit()
        return count
