"""
Audit service for logging and retrieving admin actions.

Provides business logic for audit trail management.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.repositories.audit_repository import (
    AuditRepository,
    AuditFilters,
    AuditPaginationParams,
    PaginatedAuditResult,
)

logger = logging.getLogger(__name__)


class AuditService:
    """
    Service for audit log operations.

    Handles logging admin actions and retrieving audit history.
    """

    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    def log_action(
        self,
        admin_email: str,
        action: str,
        target_type: str,
        target_id: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Log an admin action.

        Args:
            admin_email: Email of the admin performing the action
            action: The action performed
            target_type: Type of target entity
            target_id: ID of the target entity
            details: Optional additional details
            ip_address: Optional client IP address
        """
        self.audit_repo.log_action(
            admin_email=admin_email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        logger.info(
            f"Audit: {admin_email} performed '{action}' on {target_type}/{target_id}"
        )

    def get_audit_logs(
        self,
        page: int = 1,
        page_size: int = 50,
        action: Optional[str] = None,
        admin_email: Optional[str] = None,
        target_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> PaginatedAuditResult:
        """
        Get paginated audit logs with optional filters.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            action: Filter by action type
            admin_email: Filter by admin email (partial match)
            target_type: Filter by target type
            date_from: Filter by start date
            date_to: Filter by end date

        Returns:
            PaginatedAuditResult with logs and pagination info
        """
        filters = AuditFilters(
            action=action,
            admin_email=admin_email,
            target_type=target_type,
            date_from=date_from,
            date_to=date_to,
        )
        pagination = AuditPaginationParams(page=page, page_size=page_size)
        return self.audit_repo.get_logs(filters=filters, pagination=pagination)

    def get_recent_activity(self, limit: int = 10) -> List[dict]:
        """
        Get recent admin activity for dashboard.

        Args:
            limit: Maximum number of entries

        Returns:
            List of recent activity as dictionaries
        """
        logs = self.audit_repo.get_recent_logs(limit=limit)
        return [
            {
                "id": str(log.id),
                "admin_email": log.admin_email,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": log.details,
                "created_at": log.created_at,
            }
            for log in logs
        ]

    def get_filter_options(self) -> dict:
        """
        Get available filter options for the UI.

        Returns:
            Dictionary with distinct actions and admins
        """
        return {
            "actions": self.audit_repo.get_distinct_actions(),
            "admins": self.audit_repo.get_distinct_admins(),
        }
