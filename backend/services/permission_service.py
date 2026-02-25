"""
Permission service for managing user API key access.

Reads permissions from Keycloak JWT roles (realm_access.roles) and manages
role assignments via the Keycloak Admin API.
"""

import logging

import httpx

from backend.core.config import get_settings
from backend.core.security import User
from backend.infrastructure.keycloak.admin_client import get_keycloak_admin_token

logger = logging.getLogger(__name__)


class PermissionService:
    """
    Service for user permission operations.

    Reads permissions from Keycloak JWT roles and manages role assignments
    via the Keycloak Admin API.
    """

    def __init__(self):
        self.settings = get_settings()

    def get_my_permissions(self, user: User) -> dict:
        """
        Get current user's permission info from JWT roles.

        Args:
            user: The authenticated User object (roles extracted from JWT)

        Returns:
            Dictionary with permission flags
        """
        return {
            "use_hunren_keys": user.has_hunren_access,
            "is_admin": user.is_admin,
        }

    def _get_keycloak_admin_token(self) -> str | None:
        """
        Obtain an admin access token from Keycloak using the master realm.

        Delegates to the shared cached helper in admin_client.

        Returns:
            Admin access token string, or None on failure
        """
        return get_keycloak_admin_token()

    def list_users(self) -> list[dict]:
        """
        Get all users with their permission status.

        Fetches users from Keycloak Admin API and checks their realm roles
        for hunren-member or syxplain-admin.

        Returns:
            List of users with permission info (includes email)
        """
        admin_token = self._get_keycloak_admin_token()
        if not admin_token:
            logger.warning("Keycloak admin token unavailable, returning empty user list")
            return []

        try:
            admin_api_url = self.settings.auth.admin_api_url
            headers = {"Authorization": f"Bearer {admin_token}"}

            # Fetch all users
            users = []
            first = 0
            max_results = 100

            while True:
                response = httpx.get(
                    f"{admin_api_url}/users",
                    headers=headers,
                    params={"first": first, "max": max_results},
                    timeout=10.0,
                )
                response.raise_for_status()
                page_users = response.json()
                users.extend(page_users)

                if len(page_users) < max_results:
                    break
                first += max_results

            logger.info(f"Fetched {len(users)} users from Keycloak Admin API")

            # For each user, fetch their realm role mappings
            result = []
            for user in users:
                user_id = user.get("id")
                user_roles = self._get_user_realm_roles(admin_api_url, headers, user_id)
                role_names = {r.get("name") for r in user_roles}

                has_hunren = "hunren-member" in role_names or "syxplain-admin" in role_names

                result.append(
                    {
                        "user_id": user_id,
                        "email": user.get("email", ""),
                        "user_created_at": user.get("createdTimestamp"),
                        "use_hunren_keys": has_hunren,
                        "granted_by": None,
                        "permission_updated_at": None,
                    }
                )

            return result

        except Exception as e:
            logger.error(f"Failed to fetch users from Keycloak: {e}")
            return []

    def _get_user_realm_roles(
        self, admin_api_url: str, headers: dict, user_id: str
    ) -> list[dict]:
        """Fetch realm role mappings for a specific user."""
        try:
            response = httpx.get(
                f"{admin_api_url}/users/{user_id}/role-mappings/realm",
                headers=headers,
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to fetch roles for user {user_id}: {e}")
            return []

    def delete_user_permissions(self, user_id: str) -> bool:
        """
        Remove all syxplain-specific realm roles from a user (for GDPR deletion).

        Args:
            user_id: The user's Keycloak UUID

        Returns:
            True if successful, False on failure
        """
        admin_token = self._get_keycloak_admin_token()
        if not admin_token:
            return False

        admin_api_url = self.settings.auth.admin_api_url
        headers = {"Authorization": f"Bearer {admin_token}"}

        try:
            # Fetch current realm roles
            user_roles = self._get_user_realm_roles(admin_api_url, headers, user_id)

            # Filter to our app-specific roles
            app_roles = [
                {"id": r["id"], "name": r["name"]}
                for r in user_roles
                if r.get("name") in ("syxplain-admin", "hunren-member")
            ]

            if not app_roles:
                return True

            # Remove them
            response = httpx.request(
                "DELETE",
                f"{admin_api_url}/users/{user_id}/role-mappings/realm",
                headers=headers,
                json=app_roles,
                timeout=10.0,
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to delete roles for user {user_id}: {e}")
            return False
