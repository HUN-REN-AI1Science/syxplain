"""
Run service for managing analysis runs.

Encapsulates business logic for creating, querying,
and managing analysis runs.
"""

import logging
from typing import Any
from uuid import UUID

from backend.core.config import get_settings
from backend.core.exceptions import (
    ConfigurationError,
    EntityNotFoundError,
    ValidationError,
)
from backend.infrastructure.database.models import Run
from backend.infrastructure.slurm import get_slurm_backend
from backend.repositories.artifact_repository import ArtifactRepository
from backend.repositories.file_repository import FileRepository
from backend.repositories.run_repository import (
    PaginatedResult,
    PaginationParams,
    RunFilters,
    RunRepository,
)
from backend.services.file_service import FileService, get_file_service
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)


class RunService:
    """
    Service for run management operations.

    Coordinates between repositories and handles
    business logic for analysis runs.
    """

    def __init__(
        self,
        run_repo: RunRepository,
        file_repo: FileRepository,
        artifact_repo: ArtifactRepository,
        file_service: FileService | None = None,
    ):
        self.run_repo = run_repo
        self.file_repo = file_repo
        self.artifact_repo = artifact_repo
        self.file_service = file_service or get_file_service()
        self.settings = get_settings()

    def get_run_for_user(self, run_id: str, user_id: str) -> Run:
        """
        Get a run belonging to a specific user.

        Args:
            run_id: The run UUID as string
            user_id: The user UUID as string

        Returns:
            The run entity

        Raises:
            EntityNotFoundError: If run not found or not owned by user
        """
        run = self.run_repo.get_by_id_for_user(parse_uuid(run_id), parse_uuid(user_id))
        if not run:
            raise EntityNotFoundError("Run", run_id)
        return run

    def get_run_status(self, run_id: str, user_id: str) -> dict[str, Any]:
        """
        Get run status and details.

        Args:
            run_id: The run UUID as string
            user_id: The user UUID as string

        Returns:
            Status dictionary
        """
        run = self.get_run_for_user(run_id, user_id)
        return {
            "status": run.status,
            "progress": run.progress or 0,
            "error": run.error,
            "results": run.results,
            "public_share_token": run.public_share_token,
            "start_time": run.start_time,
            "finish_time": run.finish_time,
        }

    def list_runs(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 10,
        sort_field: str = "created_at",
        sort_order: str = "desc",
        status: str | None = None,
        analysis_type: str | None = None,
        search: str | None = None,
    ) -> PaginatedResult:
        """
        List runs for a user with filtering and pagination.

        Args:
            user_id: The user UUID as string
            page: Page number (1-indexed)
            page_size: Items per page
            sort_field: Field to sort by
            sort_order: Sort direction ('asc' or 'desc')
            status: Optional status filter
            analysis_type: Optional analysis type filter
            search: Optional search query

        Returns:
            PaginatedResult with runs
        """
        filters = RunFilters(status=status, analysis_type=analysis_type, search=search)
        pagination = PaginationParams(
            page=page, page_size=page_size, sort_field=sort_field, sort_order=sort_order
        )

        return self.run_repo.get_user_runs(parse_uuid(user_id), filters, pagination)

    def get_run_details(self, run_id: str, user_id: str) -> dict[str, Any]:
        """
        Get comprehensive run details including file metadata.

        Args:
            run_id: The run UUID as string
            user_id: The user UUID as string

        Returns:
            Detailed run information
        """
        run = self.get_run_for_user(run_id, user_id)

        # Get associated file metadata
        csv_metadata = None
        db_file = self.file_repo.get_latest_by_filename(run.csv_filename, UUID(user_id))

        if db_file:
            csv_metadata = self.file_service.get_csv_metadata(db_file.content, db_file.filename)

        return {
            "id": str(run.id),
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "start_time": run.start_time.isoformat() if run.start_time else None,
            "finish_time": run.finish_time.isoformat() if run.finish_time else None,
            "problem_description": run.problem_description,
            "csv_filename": run.csv_filename,
            "csv_metadata": csv_metadata,
            "analysis_type": run.analysis_type or "quick",
            "error": run.error,
        }

    def validate_run_request(
        self,
        csv_filename: str,
        target_variable: str,
        features: dict[str, str],
        analysis_type: str,
        deep_research_model: str | None,
        user_id: str,
        has_hunren_access: bool = True,
        user_api_key: str | None = None,
        user_openai_key: str | None = None,
    ) -> None:
        """
        Validate a run request before starting.

        Args:
            csv_filename: Name of the uploaded file
            target_variable: Target column name
            features: Dictionary of feature columns
            analysis_type: 'quick' or 'deep'
            deep_research_model: Model for deep analysis
            user_id: User UUID as string
            has_hunren_access: Whether user has HUN-REN key permission
            user_api_key: User-provided Gemini API key (if any)
            user_openai_key: User-provided OpenAI API key for deep research (if any)

        Raises:
            EntityNotFoundError: If file not found
            ValidationError: If configuration is invalid
            ConfigurationError: If server configuration is missing
        """
        # Check API key availability based on permissions
        if has_hunren_access:
            # User uses server keys - check server configuration
            if not self.settings.llm.openai_api_key:
                raise ConfigurationError(
                    "OPENAI_API_KEY not set on server", config_key="OPENAI_API_KEY"
                )

            # Validate deep analysis configuration for server keys
            if analysis_type == "deep":
                if not self.settings.llm.deep_research_api_key:
                    raise ConfigurationError(
                        "Deep analysis is not configured on this server. DEEP_RESEARCH_API_KEY is missing.",
                        config_key="DEEP_RESEARCH_API_KEY",
                    )

                if not deep_research_model:
                    raise ValidationError(
                        "deep_research_model is required for deep analysis",
                        field="deep_research_model",
                    )

                allowed_models = self.settings.llm.get_deep_research_model_list()
                if deep_research_model not in allowed_models:
                    raise ValidationError(
                        f"Invalid deep_research_model '{deep_research_model}'. Allowed models: {', '.join(allowed_models)}",
                        field="deep_research_model",
                        value=deep_research_model,
                    )
        else:
            # User must provide their Gemini API key
            if not user_api_key:
                raise ValidationError(
                    "API key required. Please provide your Google Gemini API key.",
                    field="user_api_keys",
                )

            # Deep analysis requires an OpenAI key and a model selection
            if analysis_type == "deep":
                if not user_openai_key:
                    raise ValidationError(
                        "Deep research requires an OpenAI API key in addition to your Gemini key.",
                        field="user_api_keys",
                    )
                if not deep_research_model:
                    raise ValidationError(
                        "deep_research_model is required for deep analysis",
                        field="deep_research_model",
                    )

        # Verify file exists and belongs to user
        db_file = self.file_repo.get_latest_by_filename(csv_filename, parse_uuid(user_id))
        if not db_file:
            raise EntityNotFoundError("File", csv_filename)

        # Validate columns exist
        df = self.file_service.parse_dataframe(db_file.content, csv_filename)
        self.file_service.validate_columns_exist(df, target_variable, features)

    async def cancel_run(self, run_id: str, user_id: str) -> bool:
        """
        Cancel a running analysis.

        - Cancels Slurm jobs if running
        - Updates database status to 'cancelled'
        - Idempotent: returns success if already complete/failed

        Args:
            run_id: The run UUID as string
            user_id: The user UUID as string

        Returns:
            True if cancellation was successful

        Raises:
            EntityNotFoundError: If run not found or not owned by user
        """
        run = self.run_repo.get_by_id_for_user(parse_uuid(run_id), parse_uuid(user_id))
        if not run:
            raise EntityNotFoundError("Run", run_id)

        # Already in terminal state - return success (idempotent)
        if run.status in ("completed", "failed", "timeout", "cancelled"):
            logger.info(f"Run {run_id} already in terminal state: {run.status}")
            return True

        # Cancel Slurm jobs if they exist
        if run.slurm_job_ids:
            backend = get_slurm_backend()
            for job_type, job_id in run.slurm_job_ids.items():
                try:
                    await backend.cancel_task(job_id)
                    logger.info(f"Cancelled {job_type}: {job_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel {job_type} {job_id}: {e}")

        # Update status in database and broadcast via WebSocket
        from backend.services.analysis_service import update_run_status

        update_run_status(run_id, status="cancelled", error="Analysis cancelled by user")

        logger.info(f"User {user_id} cancelled run {run_id}")
        return True

    def delete_run(self, run_id: str, user_id: str) -> None:
        """
        Delete a run and all associated data.

        Args:
            run_id: The run UUID as string
            user_id: The user UUID as string

        Raises:
            EntityNotFoundError: If run not found
        """
        run = self.get_run_for_user(run_id, user_id)

        # Delete artifacts first (cascade should handle this, but be explicit)
        self.artifact_repo.delete_for_run(parse_uuid(run_id))

        # Delete the run
        self.run_repo.delete_entity(run)

        logger.info(f"User {user_id} deleted run {run_id}")

    def get_artifact(self, run_id: str, filename: str, user_id: str):
        """
        Get an artifact file for download.

        Args:
            run_id: The run UUID as string
            filename: The artifact filename
            user_id: The user UUID as string

        Returns:
            The artifact entity

        Raises:
            EntityNotFoundError: If run or artifact not found
        """
        # Verify run belongs to user
        self.get_run_for_user(run_id, user_id)

        artifact = self.artifact_repo.get_by_run_and_filename(parse_uuid(run_id), filename)
        if not artifact:
            raise EntityNotFoundError("File", filename)

        return artifact

    def get_original_file(self, run_id: str, user_id: str):
        """
        Get the original uploaded file for a run.

        Args:
            run_id: The run UUID as string
            user_id: The user UUID as string

        Returns:
            The file entity

        Raises:
            EntityNotFoundError: If run or file not found
        """
        run = self.get_run_for_user(run_id, user_id)

        db_file = self.file_repo.get_latest_by_filename(run.csv_filename, parse_uuid(user_id))
        if not db_file:
            raise EntityNotFoundError("CSV file", run.csv_filename)

        return db_file
