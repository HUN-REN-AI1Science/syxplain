"""
Repository for Run entity data access.

Provides specialized queries for runs beyond basic CRUD,
including filtering, pagination, and status management.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from backend.core.constants import RunStatus
from backend.infrastructure.database.models import Run
from backend.repositories.base import BaseRepository


@dataclass
class RunFilters:
    """Filter parameters for run queries."""

    status: str | None = None
    search: str | None = None


@dataclass
class AdminRunFilters(RunFilters):
    """Extended filter parameters for admin run queries."""

    user_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass
class PaginationParams:
    """Pagination parameters for queries."""

    page: int = 1
    page_size: int = 10
    sort_field: str = "created_at"
    sort_order: str = "desc"

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass
class PaginatedResult:
    """Result container for paginated queries."""

    items: list[Run]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size


class RunRepository(BaseRepository[Run]):
    """
    Repository for Run entity with specialized query methods.

    Extends BaseRepository with run-specific operations like
    filtering by user, status, and sharing functionality.
    """

    def __init__(self, db: Session):
        super().__init__(Run, db)

    def get_by_id_for_user(self, run_id: UUID, user_id: UUID) -> Run | None:
        """
        Get a run by ID, ensuring it belongs to the specified user.

        Args:
            run_id: The run UUID
            user_id: The owner's UUID

        Returns:
            The run if found and owned by user, None otherwise
        """
        return self.db.query(Run).filter(Run.id == run_id, Run.user_id == user_id).first()

    def get_user_runs(
        self,
        user_id: UUID,
        filters: RunFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """
        Get paginated runs for a user with optional filtering.

        Args:
            user_id: The user's UUID
            filters: Optional filter criteria
            pagination: Optional pagination parameters

        Returns:
            PaginatedResult with runs and metadata
        """
        filters = filters or RunFilters()
        pagination = pagination or PaginationParams()

        # Base query for user's runs
        query = self.db.query(Run).filter(Run.user_id == user_id)

        # Apply filters
        if filters.status:
            query = query.filter(Run.status == filters.status)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(
                or_(
                    Run.csv_filename.ilike(search_pattern),
                    Run.problem_description["target_variable"].astext.ilike(search_pattern),
                )
            )

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        sort_columns = {
            "created_at": Run.created_at,
            "csv_filename": Run.csv_filename,
            "status": Run.status,
            "target_variable": Run.problem_description["target_variable"].astext,
        }
        sort_column = sort_columns.get(pagination.sort_field, Run.created_at)

        if pagination.sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Apply pagination
        items = query.offset(pagination.offset).limit(pagination.page_size).all()

        return PaginatedResult(
            items=items, total=total, page=pagination.page, page_size=pagination.page_size
        )

    def get_by_share_token(self, token: str) -> Run | None:
        """
        Get a run by its public share token.

        Args:
            token: The share token string

        Returns:
            The run if found, None otherwise
        """
        return self.db.query(Run).filter(Run.public_share_token == token).first()

    def get_shared_runs(self, user_id: UUID) -> list[Run]:
        """
        Get all runs shared by a user.

        Args:
            user_id: The user's UUID

        Returns:
            List of shared runs
        """
        return (
            self.db.query(Run)
            .filter(Run.user_id == user_id, Run.public_share_token.isnot(None))
            .order_by(Run.created_at.desc())
            .all()
        )

    def update_status(
        self,
        run_id: UUID,
        status: str,
        results: dict[str, Any] | None = None,
        error: str | None = None,
        progress: int | None = None,
    ) -> Run | None:
        """
        Update run status and related fields.

        Args:
            run_id: The run UUID
            status: New status value
            results: Optional results data
            error: Optional error message
            progress: Optional progress percentage

        Returns:
            Updated run or None if not found
        """
        run = self.get_by_id(run_id)
        if not run:
            return None

        run.status = status
        # Set start_time when transitioning to running
        if status == RunStatus.RUNNING and run.start_time is None:
            run.start_time = datetime.utcnow()
        # Set finish_time for terminal states
        if RunStatus.is_terminal(status):
            run.finish_time = datetime.utcnow()
        if results is not None:
            run.results = results
        if error is not None:
            run.error = error
        if progress is not None:
            run.progress = progress
        elif status == RunStatus.COMPLETED:
            run.progress = 100

        self.db.commit()
        return run

    def update_progress(self, run_id: UUID, progress: int) -> Run | None:
        """
        Update run progress percentage.

        Args:
            run_id: The run UUID
            progress: Progress percentage (0-100)

        Returns:
            Updated run or None if not found
        """
        run = self.get_by_id(run_id)
        if run:
            run.progress = min(99, max(0, progress))
            self.db.commit()
        return run

    def set_share_token(self, run_id: UUID, token: str) -> Run | None:
        """
        Set or update the share token for a run.

        Args:
            run_id: The run UUID
            token: The share token string

        Returns:
            Updated run or None if not found
        """
        run = self.get_by_id(run_id)
        if run:
            run.public_share_token = token
            self.db.commit()
        return run

    def revoke_share_token(self, run_id: UUID) -> Run | None:
        """
        Remove the share token from a run.

        Args:
            run_id: The run UUID

        Returns:
            Updated run or None if not found
        """
        run = self.get_by_id(run_id)
        if run:
            run.public_share_token = None
            self.db.commit()
        return run

    def get_stale_runs(self, timeout_hours: float) -> list[Run]:
        """
        Get runs that have exceeded the timeout period.

        Args:
            timeout_hours: Number of hours after which runs are considered stale

        Returns:
            List of stale runs
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)
        return (
            self.db.query(Run)
            .filter(Run.status.in_(["running", "pending"]), Run.created_at < cutoff_time)
            .all()
        )

    def count_for_user(self, user_id: UUID) -> int:
        """
        Count total runs for a user.

        Args:
            user_id: The user's UUID

        Returns:
            Total run count
        """
        return self.db.query(Run).filter(Run.user_id == user_id).count()

    def get_earliest_for_user(self, user_id: UUID) -> Run | None:
        """
        Get the earliest run for a user.

        Args:
            user_id: The user's UUID

        Returns:
            Earliest run or None
        """
        return (
            self.db.query(Run).filter(Run.user_id == user_id).order_by(Run.created_at.asc()).first()
        )

    def delete_all_for_user(self, user_id: UUID) -> int:
        """
        Delete all runs for a user (GDPR deletion).

        Args:
            user_id: The user's UUID

        Returns:
            Number of runs deleted
        """
        count = self.db.query(Run).filter(Run.user_id == user_id).delete()
        self.db.commit()
        return count

    # =========================================================================
    # Admin Methods
    # =========================================================================

    def get_all_runs(
        self,
        filters: AdminRunFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult:
        """
        Get all runs across all users with optional filtering (admin only).

        Args:
            filters: Optional filter criteria including user_id, dates
            pagination: Optional pagination parameters

        Returns:
            PaginatedResult with runs and metadata
        """
        filters = filters or AdminRunFilters()
        pagination = pagination or PaginationParams()

        query = self.db.query(Run)

        # Apply filters
        if filters.status:
            query = query.filter(Run.status == filters.status)
        if filters.search:
            search_pattern = f"%{filters.search}%"
            query = query.filter(
                or_(
                    Run.csv_filename.ilike(search_pattern),
                    Run.problem_description["target_variable"].astext.ilike(search_pattern),
                )
            )
        if filters.user_id:
            try:
                user_uuid = UUID(filters.user_id)
                query = query.filter(Run.user_id == user_uuid)
            except ValueError:
                pass
        if filters.date_from:
            query = query.filter(Run.created_at >= filters.date_from)
        if filters.date_to:
            query = query.filter(Run.created_at <= filters.date_to)

        # Get total count before pagination
        total = query.count()

        # Apply sorting
        sort_columns = {
            "created_at": Run.created_at,
            "csv_filename": Run.csv_filename,
            "status": Run.status,
        }
        sort_column = sort_columns.get(pagination.sort_field, Run.created_at)

        if pagination.sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Apply pagination
        items = query.offset(pagination.offset).limit(pagination.page_size).all()

        return PaginatedResult(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    def admin_get_run(self, run_id: UUID) -> Run | None:
        """
        Get a run by ID without user restriction (admin only).

        Args:
            run_id: The run UUID

        Returns:
            The run if found, None otherwise
        """
        return self.get_by_id(run_id)

    def admin_cancel_run(self, run_id: UUID) -> Run | None:
        """
        Cancel a run (admin only).

        Args:
            run_id: The run UUID

        Returns:
            Updated run or None if not found
        """
        run = self.get_by_id(run_id)
        if not run:
            return None

        if run.status in (RunStatus.PENDING, RunStatus.RUNNING):
            run.status = RunStatus.CANCELLED
            run.finish_time = datetime.utcnow()
            self.db.commit()
            self.db.refresh(run)

        return run

    def admin_delete_run(self, run_id: UUID) -> bool:
        """
        Delete a run and all associated data (admin only).

        Args:
            run_id: The run UUID

        Returns:
            True if deleted, False if not found
        """
        run = self.get_by_id(run_id)
        if not run:
            return False

        self.db.delete(run)
        self.db.commit()
        return True

    def get_failed_runs(
        self,
        days: int = 30,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedResult:
        """
        Get failed and timeout runs (admin only).

        Args:
            days: Number of days to look back
            page: Page number
            page_size: Items per page

        Returns:
            PaginatedResult with failed runs
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        query = self.db.query(Run).filter(
            Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT]),
            Run.created_at >= cutoff,
        )

        total = query.count()
        offset = (page - 1) * page_size

        items = query.order_by(desc(Run.created_at)).offset(offset).limit(page_size).all()

        return PaginatedResult(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
