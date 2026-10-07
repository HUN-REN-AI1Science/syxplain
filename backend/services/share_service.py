"""
Share service for managing public sharing of runs.

Encapsulates business logic for creating and revoking
share links for analysis runs.
"""

import logging
import secrets
from typing import Any
from uuid import UUID

from backend.core.exceptions import EntityNotFoundError
from backend.repositories.file_repository import FileRepository
from backend.repositories.run_repository import RunRepository
from backend.services.file_service import FileService, get_file_service
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)


class ShareService:
    """
    Service for sharing operations.

    Handles creating and revoking public share links
    and retrieving shared run data.
    """

    # 32 bytes = 256 bits of entropy, produces ~43 character URL-safe token
    # This provides strong protection against enumeration attacks
    SHARE_TOKEN_LENGTH = 32

    def __init__(
        self,
        run_repo: RunRepository,
        file_repo: FileRepository,
        file_service: FileService | None = None,
    ):
        self.run_repo = run_repo
        self.file_repo = file_repo
        self.file_service = file_service or get_file_service()

    def create_share_link(self, run_id: str, user_id: str) -> dict[str, str]:
        """
        Create a public share link for a run.

        If the run already has a share token, returns the existing link.

        Args:
            run_id: The run UUID as string
            user_id: The owner's UUID as string

        Returns:
            Dictionary with share_token and share_url

        Raises:
            EntityNotFoundError: If run not found or not owned by user
            ValueError: If run has incomplete results (explanation error)
        """
        run = self.run_repo.get_by_id_for_user(UUID(run_id), UUID(user_id))
        if not run:
            raise EntityNotFoundError("Run", run_id)

        # Block sharing if explanations failed
        if self._has_explanation_error(run.results):
            raise ValueError(
                "Cannot share results: AI explanations could not be generated for this analysis. "
                "Please re-run the analysis to get complete results before sharing."
            )

        # If already shared, return existing token
        if run.public_share_token:
            return {
                "share_token": run.public_share_token,
                "share_url": f"/share/{run.public_share_token}",
            }

        # Generate new token
        token = secrets.token_urlsafe(self.SHARE_TOKEN_LENGTH)
        self.run_repo.set_share_token(parse_uuid(run_id), token)

        logger.info(f"User {user_id} created share link for run {run_id}")

        return {"share_token": token, "share_url": f"/share/{token}"}

    @staticmethod
    def _has_explanation_error(results: dict | None) -> bool:
        """
        Check if the run's results are incomplete because the explanation failed.

        Runs with a discovery report are complete without the narration (the equations,
        metrics and agent report are all there), so they can always be shared.
        """
        if isinstance(results, dict) and results.get("discovery"):
            return False
        if not results or not isinstance(results, dict):
            return False
        explanations = results.get("explanations")
        return isinstance(explanations, dict) and "error" in explanations

    def revoke_share_link(self, run_id: str, user_id: str) -> None:
        """
        Revoke a public share link for a run.

        Args:
            run_id: The run UUID as string
            user_id: The owner's UUID as string

        Raises:
            EntityNotFoundError: If run not found or not owned by user
        """
        run = self.run_repo.get_by_id_for_user(parse_uuid(run_id), parse_uuid(user_id))
        if not run:
            raise EntityNotFoundError("Run", run_id)

        self.run_repo.revoke_share_token(parse_uuid(run_id))

        logger.info(f"User {user_id} revoked share link for run {run_id}")

    def get_shared_runs(self, user_id: str) -> list[dict[str, Any]]:
        """
        Get all runs shared by a user.

        Args:
            user_id: The user's UUID as string

        Returns:
            List of shared run summaries
        """
        runs = self.run_repo.get_shared_runs(parse_uuid(user_id))

        result = []
        for run in runs:
            result.append(
                {
                    "id": str(run.id),
                    "target_variable": run.target_variable,
                    "csv_filename": run.csv_filename,
                    "analysis_type": run.analysis_type or "quick",
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "share_token": run.public_share_token,
                    "share_url": f"/share/{run.public_share_token}",
                }
            )

        return result

    def get_public_run(self, share_token: str) -> dict[str, Any]:
        """
        Get run results by share token (no auth required).

        Args:
            share_token: The public share token

        Returns:
            Public run data

        Raises:
            EntityNotFoundError: If shared run not found
        """
        run = self.run_repo.get_by_share_token(share_token)
        if not run:
            raise EntityNotFoundError("Shared run", share_token)

        pd = run.problem_description or {}
        return {
            "status": run.status,
            "progress": run.progress or 0,
            "results": run.results,
            "share_token": run.public_share_token,
            "target_variable": pd.get("target_variable"),
        }

    def get_public_run_details(self, share_token: str) -> dict[str, Any]:
        """
        Get detailed run information by share token (no auth required).

        Args:
            share_token: The public share token

        Returns:
            Detailed public run data

        Raises:
            EntityNotFoundError: If shared run not found
        """
        run = self.run_repo.get_by_share_token(share_token)
        if not run:
            raise EntityNotFoundError("Shared run", share_token)

        # Get associated file metadata
        csv_metadata = None
        db_file = self.file_repo.get_latest_by_filename(run.csv_filename, run.user_id)

        if db_file:
            csv_metadata = self.file_service.get_csv_metadata(db_file.content, db_file.filename)

        return {
            "id": str(run.id),
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "problem_description": run.problem_description,
            "csv_filename": run.csv_filename,
            "csv_metadata": csv_metadata,
            "analysis_type": run.analysis_type or "quick",
            "error": run.error,
        }

    def get_public_file(self, share_token: str):
        """
        Get the original file for a shared run (no auth required).

        Args:
            share_token: The public share token

        Returns:
            The file entity

        Raises:
            EntityNotFoundError: If shared run or file not found
        """
        run = self.run_repo.get_by_share_token(share_token)
        if not run:
            raise EntityNotFoundError("Shared run", share_token)

        db_file = self.file_repo.get_latest_by_filename(run.csv_filename, run.user_id)
        if not db_file:
            raise EntityNotFoundError("CSV file", run.csv_filename)

        return db_file
