"""
Repository for audit log data access.

Handles CRUD operations for AuditLog entities.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.infrastructure.database.models import AuditLog
from backend.repositories.base import BaseRepository


@dataclass
class AuditFilters:
    """Filter parameters for audit log queries."""

    action: str | None = None
    admin_email: str | None = None
    target_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass
class AuditPaginationParams:
    """Pagination parameters for audit queries."""

    page: int = 1
    page_size: int = 50

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass
class PaginatedAuditResult:
    """Result container for paginated audit queries."""

    items: list[AuditLog]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size


class AuditRepository(BaseRepository[AuditLog]):
    """
    Repository for managing audit logs.

    Provides methods for creating and querying admin action logs.
    """

    def __init__(self, db: Session):
        """Initialize with AuditLog model."""
        super().__init__(AuditLog, db)

    def log_action(
        self,
        admin_email: str,
        action: str,
        target_type: str,
        target_id: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """
        Create a new audit log entry.

        Args:
            admin_email: Email of the admin performing the action
            action: The action performed (e.g., "grant_permission", "delete_run")
            target_type: Type of target (e.g., "user", "run")
            target_id: ID of the target entity
            details: Optional additional details as JSON
            ip_address: Optional client IP address

        Returns:
            The created AuditLog entry
        """
        audit_log = AuditLog(
            admin_email=admin_email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        return self.create(audit_log)

    def get_logs(
        self,
        filters: AuditFilters | None = None,
        pagination: AuditPaginationParams | None = None,
    ) -> PaginatedAuditResult:
        """
        Get paginated audit logs with optional filtering.

        Args:
            filters: Optional filter criteria
            pagination: Optional pagination parameters

        Returns:
            PaginatedAuditResult with logs and metadata
        """
        filters = filters or AuditFilters()
        pagination = pagination or AuditPaginationParams()

        query = self.db.query(AuditLog)

        # Apply filters
        if filters.action:
            query = query.filter(AuditLog.action == filters.action)
        if filters.admin_email:
            query = query.filter(AuditLog.admin_email.ilike(f"%{filters.admin_email}%"))
        if filters.target_type:
            query = query.filter(AuditLog.target_type == filters.target_type)
        if filters.date_from:
            query = query.filter(AuditLog.created_at >= filters.date_from)
        if filters.date_to:
            query = query.filter(AuditLog.created_at <= filters.date_to)

        # Get total count before pagination
        total = query.count()

        # Apply sorting (newest first)
        query = query.order_by(desc(AuditLog.created_at))

        # Apply pagination
        items = query.offset(pagination.offset).limit(pagination.page_size).all()

        return PaginatedAuditResult(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    def get_recent_logs(self, limit: int = 10) -> list[AuditLog]:
        """
        Get the most recent audit logs.

        Args:
            limit: Maximum number of logs to return

        Returns:
            List of recent AuditLog entries
        """
        return self.db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit).all()

    def get_actions_by_admin(self, admin_email: str, days: int = 30) -> list[AuditLog]:
        """
        Get all actions by a specific admin in recent days.

        Args:
            admin_email: The admin's email
            days: Number of days to look back

        Returns:
            List of AuditLog entries
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        return (
            self.db.query(AuditLog)
            .filter(
                AuditLog.admin_email == admin_email,
                AuditLog.created_at >= cutoff,
            )
            .order_by(desc(AuditLog.created_at))
            .all()
        )

    def get_distinct_actions(self) -> list[str]:
        """
        Get list of distinct action types.

        Returns:
            List of unique action strings
        """
        result = self.db.query(AuditLog.action).distinct().all()
        return [r[0] for r in result]

    def get_distinct_admins(self) -> list[str]:
        """
        Get list of distinct admin emails.

        Returns:
            List of unique admin email strings
        """
        result = self.db.query(AuditLog.admin_email).distinct().all()
        return [r[0] for r in result]
