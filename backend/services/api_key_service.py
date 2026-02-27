"""
API key service for key generation, authentication, and management.

Handles the business logic for creating, validating, and revoking API keys.
Keys are SHA-256 hashed (not bcrypt) because they are 256-bit random strings
immune to dictionary attacks, and SHA-256 enables direct DB index lookup.

Each user may have at most one active key at a time.
"""

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Any

from backend.core.config import get_settings
from backend.core.exceptions import AuthenticationError, ValidationError
from backend.core.security import User
from backend.infrastructure.database.models import ApiKey
from backend.infrastructure.keycloak.admin_client import get_keycloak_admin_token
from backend.repositories.api_key_repository import ApiKeyRepository
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)

KEY_PREFIX = "syxp_"
ROLE_CACHE_TTL_SECONDS = 3600  # 1 hour


def _generate_key() -> str:
    """Generate a new API key: syxp_ + 32 bytes of URL-safe randomness."""
    return KEY_PREFIX + secrets.token_urlsafe(32)


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash of the raw key for storage and lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKeyService:
    """Service for API key lifecycle management and authentication."""

    def __init__(self, api_key_repo: ApiKeyRepository):
        self.repo = api_key_repo
        self.settings = get_settings()

    def create_key(self, user: User) -> dict[str, Any]:
        """
        Generate a new API key for the user.

        Returns the full key exactly once. It cannot be retrieved again.

        Raises:
            ValidationError: If the user already has an active key.
        """
        user_uuid = parse_uuid(user.user_id)
        existing = self.repo.get_active_for_user(user_uuid)
        if existing:
            raise ValidationError(
                "You already have an active API key. Revoke it first or use regenerate.",
                field="api_keys",
            )

        raw_key = _generate_key()
        key_hash = _hash_key(raw_key)

        api_key = ApiKey(
            user_id=user_uuid,
            name="default",
            key_prefix=raw_key[:12],
            key_hash=key_hash,
            user_email=user.email,
            user_roles=user.roles,
            expires_at=None,
        )
        self.repo.create(api_key)

        logger.info(f"API key created for user {user.user_id}")

        return {
            "id": str(api_key.id),
            "key": raw_key,  # shown once only
            "key_prefix": api_key.key_prefix,
            "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        }

    def get_current_key(self, user_id: str) -> dict[str, Any] | None:
        """Get the user's active API key info, or None if no active key."""
        user_uuid = parse_uuid(user_id)
        key = self.repo.get_active_for_user(user_uuid)
        if not key:
            return None
        return {
            "id": str(key.id),
            "key_prefix": key.key_prefix,
            "is_active": key.is_active,
            "created_at": key.created_at.isoformat() if key.created_at else None,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        }

    def revoke_current_key(self, user_id: str) -> None:
        """
        Revoke the user's active API key.

        Raises:
            ValidationError: If no active key exists.
        """
        user_uuid = parse_uuid(user_id)
        key = self.repo.get_active_for_user(user_uuid)
        if not key:
            raise ValidationError("No active API key to revoke", field="api_keys")
        self.repo.deactivate(key)
        logger.info(f"API key revoked for user {user_id}")

    def regenerate_key(self, user: User) -> dict[str, Any]:
        """
        Revoke the current key and create a new one.

        Raises:
            ValidationError: If no active key exists to regenerate.
        """
        user_uuid = parse_uuid(user.user_id)
        old_key = self.repo.get_active_for_user(user_uuid)
        if not old_key:
            raise ValidationError("No active API key to regenerate", field="api_keys")

        self.repo.deactivate(old_key)
        return self.create_key(user)

    def authenticate_by_api_key(self, raw_key: str) -> User:
        """
        Authenticate a request using a raw API key.

        Looks up the key by hash, checks active/expired status,
        updates last_used_at, and returns a User object.

        Raises:
            AuthenticationError: If key is invalid, inactive, or expired.
        """
        key_hash = _hash_key(raw_key)
        api_key = self.repo.get_active_by_key_hash(key_hash)

        if not api_key:
            raise AuthenticationError(message="Invalid API key", reason="not_found")

        # Update last used timestamp
        self.repo.update_last_used(api_key)

        # Refresh roles from Keycloak if stale
        self._maybe_refresh_roles(api_key)

        return User(
            user_id=str(api_key.user_id),
            email=api_key.user_email,
            roles=api_key.user_roles or [],
        )

    def _maybe_refresh_roles(self, api_key: ApiKey) -> None:
        """
        Refresh cached roles from Keycloak if they are older than TTL.

        This is best-effort: if Keycloak is unreachable, we use stale roles.
        """
        if api_key.last_used_at:
            age = (datetime.utcnow() - api_key.last_used_at).total_seconds()
            if age < ROLE_CACHE_TTL_SECONDS:
                return

        try:
            admin_token = get_keycloak_admin_token()
            if not admin_token:
                return

            auth_settings = self.settings.auth
            import httpx as httpx_sync

            # Synchronous call — this runs rarely (once per hour per key)
            with httpx_sync.Client() as client:
                resp = client.get(
                    f"{auth_settings.admin_api_url}/users/{api_key.user_id}/role-mappings/realm",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    roles = [r["name"] for r in resp.json()]
                    self.repo.update_roles(api_key, roles)
                    logger.debug(f"Refreshed roles for API key {api_key.key_prefix}: {roles}")
        except Exception as e:
            logger.debug(f"Could not refresh roles for API key {api_key.key_prefix}: {e}")
