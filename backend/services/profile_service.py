"""
Profile service for user profile management.

Encapsulates business logic for profile data and GDPR deletion.
"""

import logging
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.core.exceptions import ExternalServiceError
from backend.infrastructure.keycloak.admin_client import get_keycloak_admin_token
from backend.repositories.file_repository import FileRepository
from backend.repositories.run_repository import RunRepository
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)


class ProfileService:
    """
    Service for user profile operations.

    Handles profile data retrieval and GDPR-compliant account deletion.
    """

    def __init__(self, run_repo: RunRepository, file_repo: FileRepository):
        self.run_repo = run_repo
        self.file_repo = file_repo
        self.settings = get_settings()

    def get_profile(self, user_id: str, email: str) -> dict[str, Any]:
        """
        Get user profile information.

        Args:
            user_id: The user's UUID as string
            email: The user's email address

        Returns:
            Profile data dictionary
        """
        user_uuid = parse_uuid(user_id)

        total_runs = self.run_repo.count_for_user(user_uuid)
        total_files = self.file_repo.count_for_user(user_uuid)

        # Get earliest activity timestamp
        earliest_run = self.run_repo.get_earliest_for_user(user_uuid)
        earliest_file = self.file_repo.get_earliest_for_user(user_uuid)

        created_at = None
        if earliest_run and earliest_file:
            earliest = min(earliest_run.created_at, earliest_file.created_at)
            created_at = earliest.isoformat()
        elif earliest_run:
            created_at = earliest_run.created_at.isoformat()
        elif earliest_file:
            created_at = earliest_file.created_at.isoformat()

        return {
            "email": email,
            "created_at": created_at,
            "total_runs": total_runs,
            "total_files": total_files,
        }

    async def delete_account(self, user_id: str) -> None:
        """
        GDPR-compliant account deletion.

        Removes all user data from the database and
        deletes the user from Keycloak.

        Args:
            user_id: The user's UUID as string

        Raises:
            ExternalServiceError: If Keycloak deletion fails
        """
        user_uuid = parse_uuid(user_id)

        logger.info(f"Starting GDPR account deletion for user: {user_id}")

        # Delete all runs (cascades to run_steps and run_artifacts)
        runs_deleted = self.run_repo.delete_all_for_user(user_uuid)
        logger.info(f"Deleted {runs_deleted} runs for user {user_id}")

        # Delete all files
        files_deleted = self.file_repo.delete_all_for_user(user_uuid)
        logger.info(f"Deleted {files_deleted} files for user {user_id}")

        # Delete user from Keycloak
        await self._delete_keycloak_user(user_id)

        logger.info(f"GDPR deletion completed for user {user_id}")

    async def _delete_keycloak_user(self, user_id: str) -> None:
        """
        Delete a user from Keycloak using the Admin REST API.

        Args:
            user_id: The user's UUID as string

        Raises:
            ExternalServiceError: If deletion fails
        """
        admin_token = get_keycloak_admin_token()
        if not admin_token:
            logger.warning("Keycloak admin token unavailable, skipping user deletion")
            return

        auth = self.settings.auth

        try:
            async with httpx.AsyncClient() as client:
                delete_response = await client.delete(
                    f"{auth.admin_api_url}/users/{user_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=10.0,
                )

                if delete_response.status_code in (200, 204):
                    logger.info(f"Successfully deleted Keycloak user: {user_id}")
                elif delete_response.status_code == 404:
                    logger.warning(f"Keycloak user not found (may already be deleted): {user_id}")
                else:
                    error_detail = delete_response.text
                    logger.error(
                        f"Failed to delete Keycloak user {user_id}: "
                        f"{delete_response.status_code} - {error_detail}"
                    )
                    raise ExternalServiceError(
                        service="Keycloak",
                        message=f"Failed to delete user from authentication provider: {error_detail}",
                    )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error deleting Keycloak user {user_id}: {e}")
            raise ExternalServiceError(
                service="Keycloak",
                message=f"Failed to connect to authentication provider: {e}",
            )
