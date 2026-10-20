"""
Admin stats service for dashboard metrics and analytics.

Provides aggregated statistics and trend data for the admin dashboard.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.core.constants import RunStatus
from backend.infrastructure.database.models import Run

logger = logging.getLogger(__name__)


class AdminStatsService:
    """
    Service for admin dashboard statistics.

    Handles aggregation queries for metrics, trends, and analytics.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_dashboard_stats(self) -> dict:
        """
        Get key dashboard metrics.

        Returns:
            Dictionary with:
            - total_users: Total registered users
            - active_users_24h: Users with runs in last 24 hours
            - total_runs: Total number of runs
            - runs_today: Runs created today
            - success_rate: Percentage of completed runs
            - avg_duration_seconds: Average run duration
            - pending_runs: Number of pending runs
            - running_runs: Number of currently running runs
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = now - timedelta(hours=24)

        # Total users (from permissions or Keycloak)
        total_users = self.db.query(func.count(func.distinct(Run.user_id))).scalar() or 0

        # Active users in last 24 hours
        active_users_24h = (
            self.db.query(func.count(func.distinct(Run.user_id)))
            .filter(Run.created_at >= yesterday)
            .scalar()
            or 0
        )

        # Total runs
        total_runs = self.db.query(func.count(Run.id)).scalar() or 0

        # Runs today
        runs_today = (
            self.db.query(func.count(Run.id)).filter(Run.created_at >= today_start).scalar() or 0
        )

        # Success rate (completed / (completed + failed + timeout))
        terminal_runs = (
            self.db.query(Run)
            .filter(Run.status.in_([RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.TIMEOUT]))
            .count()
        )
        completed_runs = self.db.query(Run).filter(Run.status == RunStatus.COMPLETED).count()
        success_rate = (completed_runs / terminal_runs * 100) if terminal_runs > 0 else 0.0

        # Average duration (for completed runs with timestamps)
        avg_duration = (
            self.db.query(
                func.avg(
                    func.extract("epoch", Run.finish_time) - func.extract("epoch", Run.start_time)
                )
            )
            .filter(
                Run.status == RunStatus.COMPLETED,
                Run.start_time.isnot(None),
                Run.finish_time.isnot(None),
            )
            .scalar()
        )
        avg_duration_seconds = float(avg_duration) if avg_duration else 0.0

        # Pending and running counts
        pending_runs = self.db.query(Run).filter(Run.status == RunStatus.PENDING).count()
        running_runs = self.db.query(Run).filter(Run.status == RunStatus.RUNNING).count()

        return {
            "total_users": total_users,
            "active_users_24h": active_users_24h,
            "total_runs": total_runs,
            "runs_today": runs_today,
            "success_rate": round(success_rate, 1),
            "avg_duration_seconds": round(avg_duration_seconds, 1),
            "pending_runs": pending_runs,
            "running_runs": running_runs,
        }

    def get_run_trends(self, days: int = 30) -> list[dict]:
        """
        Get daily run counts with status breakdown.

        Args:
            days: Number of days to include

        Returns:
            List of daily trend data with date, total, completed, failed counts
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Group runs by date and status
        results = (
            self.db.query(
                func.date(Run.created_at).label("date"),
                func.count(Run.id).label("total"),
                func.sum(case((Run.status == RunStatus.COMPLETED, 1), else_=0)).label("completed"),
                func.sum(case((Run.status == RunStatus.FAILED, 1), else_=0)).label("failed"),
                func.sum(case((Run.status == RunStatus.TIMEOUT, 1), else_=0)).label("timeout"),
                func.sum(case((Run.status == RunStatus.CANCELLED, 1), else_=0)).label("cancelled"),
            )
            .filter(Run.created_at >= cutoff)
            .group_by(func.date(Run.created_at))
            .order_by(func.date(Run.created_at))
            .all()
        )

        return [
            {
                "date": str(r.date),
                "total": r.total,
                "completed": r.completed or 0,
                "failed": r.failed or 0,
                "timeout": r.timeout or 0,
                "cancelled": r.cancelled or 0,
            }
            for r in results
        ]

    def get_status_distribution(self) -> list[dict]:
        """
        Get current distribution of run statuses.

        Returns:
            List of status counts
        """
        results = (
            self.db.query(Run.status, func.count(Run.id).label("count")).group_by(Run.status).all()
        )

        return [{"status": r.status, "count": r.count} for r in results]

    def get_analysis_type_distribution(self) -> list[dict]:
        """
        Get distribution of analysis types (quick vs deep).

        Returns:
            List of type counts
        """
        results = (
            self.db.query(Run.analysis_type, func.count(Run.id).label("count"))
            .group_by(Run.analysis_type)
            .all()
        )

        return [{"type": r.analysis_type, "count": r.count} for r in results]

    def get_user_growth(self, days: int = 90) -> list[dict]:
        """
        Get daily new user signup counts.

        Args:
            days: Number of days to include

        Returns:
            List of daily user counts
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Count distinct users by their first run date
        subquery = (
            self.db.query(
                Run.user_id,
                func.min(Run.created_at).label("first_run"),
            )
            .group_by(Run.user_id)
            .subquery()
        )

        results = (
            self.db.query(
                func.date(subquery.c.first_run).label("date"),
                func.count(subquery.c.user_id).label("count"),
            )
            .filter(subquery.c.first_run >= cutoff)
            .group_by(func.date(subquery.c.first_run))
            .order_by(func.date(subquery.c.first_run))
            .all()
        )

        return [{"date": str(r.date), "count": r.count} for r in results]

    def get_top_users(self, limit: int = 10, period_days: int = 30) -> list[dict]:
        """
        Get top users by run count in recent period.

        Args:
            limit: Maximum number of users to return
            period_days: Period to consider

        Returns:
            List of user stats
        """
        cutoff = datetime.utcnow() - timedelta(days=period_days)

        results = (
            self.db.query(
                Run.user_id,
                func.count(Run.id).label("run_count"),
                func.sum(case((Run.status == RunStatus.COMPLETED, 1), else_=0)).label("completed"),
            )
            .filter(Run.created_at >= cutoff)
            .group_by(Run.user_id)
            .order_by(func.count(Run.id).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "user_id": str(r.user_id),
                "run_count": r.run_count,
                "completed": r.completed or 0,
            }
            for r in results
        ]

    def get_performance_stats(self) -> dict:
        """
        Get performance analytics.

        Returns:
            Dictionary with duration stats and success rate
        """
        # Duration statistics for completed runs
        durations = (
            self.db.query(
                func.extract("epoch", Run.finish_time) - func.extract("epoch", Run.start_time)
            )
            .filter(
                Run.status == RunStatus.COMPLETED,
                Run.start_time.isnot(None),
                Run.finish_time.isnot(None),
            )
            .all()
        )

        duration_values = [d[0] for d in durations if d[0] is not None]

        if duration_values:
            sorted_durations = sorted(duration_values)
            avg_duration = sum(duration_values) / len(duration_values)
            median_duration = sorted_durations[len(sorted_durations) // 2]
            p95_index = int(len(sorted_durations) * 0.95)
            p95_duration = sorted_durations[min(p95_index, len(sorted_durations) - 1)]
        else:
            avg_duration = median_duration = p95_duration = 0.0

        # Success rate
        terminal_runs = (
            self.db.query(Run)
            .filter(Run.status.in_([RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.TIMEOUT]))
            .count()
        )
        completed_runs = self.db.query(Run).filter(Run.status == RunStatus.COMPLETED).count()
        success_rate = (completed_runs / terminal_runs * 100) if terminal_runs > 0 else 0.0

        return {
            "avg_duration": round(avg_duration, 1),
            "median_duration": round(median_duration, 1),
            "p95_duration": round(p95_duration, 1),
            "success_rate": round(success_rate, 1),
            "total_completed": completed_runs,
        }

    def get_performance_by_type(self) -> list[dict]:
        """
        Get performance metrics grouped by analysis type.

        Returns:
            List of per-type performance stats
        """
        types = [
            t
            for (t,) in self.db.query(Run.analysis_type).distinct().order_by(Run.analysis_type)
            if t
        ]
        result = []

        for analysis_type in types:
            # Duration stats
            durations = (
                self.db.query(
                    func.extract("epoch", Run.finish_time) - func.extract("epoch", Run.start_time)
                )
                .filter(
                    Run.analysis_type == analysis_type,
                    Run.status == RunStatus.COMPLETED,
                    Run.start_time.isnot(None),
                    Run.finish_time.isnot(None),
                )
                .all()
            )

            duration_values = [d[0] for d in durations if d[0] is not None]
            avg_duration = sum(duration_values) / len(duration_values) if duration_values else 0

            # Counts
            total = self.db.query(Run).filter(Run.analysis_type == analysis_type).count()
            completed = (
                self.db.query(Run)
                .filter(Run.analysis_type == analysis_type, Run.status == RunStatus.COMPLETED)
                .count()
            )
            failed = (
                self.db.query(Run)
                .filter(
                    Run.analysis_type == analysis_type,
                    Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT]),
                )
                .count()
            )

            success_rate = (
                (completed / (completed + failed) * 100) if (completed + failed) > 0 else 0
            )

            result.append(
                {
                    "type": analysis_type,
                    "total_runs": total,
                    "completed": completed,
                    "failed": failed,
                    "avg_duration": round(avg_duration, 1),
                    "success_rate": round(success_rate, 1),
                }
            )

        return result

    def get_error_distribution(self, days: int = 30) -> list[dict]:
        """
        Get error types grouped by frequency.

        Args:
            days: Number of days to include

        Returns:
            List of error patterns with counts
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get failed runs with errors
        failed_runs = (
            self.db.query(Run.error)
            .filter(
                Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT]),
                Run.error.isnot(None),
                Run.created_at >= cutoff,
            )
            .all()
        )

        # Simple categorization of errors
        error_counts: dict[str, int] = {}
        for (error,) in failed_runs:
            # Categorize by common error patterns
            if not error:
                category = "Unknown Error"
            elif "timeout" in error.lower():
                category = "Timeout"
            elif "api" in error.lower() or "rate" in error.lower():
                category = "API Error"
            elif "file" in error.lower() or "csv" in error.lower():
                category = "File Error"
            elif "memory" in error.lower() or "resource" in error.lower():
                category = "Resource Error"
            elif "slurm" in error.lower():
                category = "Slurm Error"
            else:
                category = "Other Error"

            error_counts[category] = error_counts.get(category, 0) + 1

        return [
            {"error_type": k, "count": v}
            for k, v in sorted(error_counts.items(), key=lambda x: -x[1])
        ]

    def get_error_trend(self, days: int = 30) -> list[dict]:
        """
        Get daily failure rate trend.

        Args:
            days: Number of days to include

        Returns:
            List of daily failure rates
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        results = (
            self.db.query(
                func.date(Run.created_at).label("date"),
                func.count(Run.id).label("total"),
                func.sum(
                    case((Run.status.in_([RunStatus.FAILED, RunStatus.TIMEOUT]), 1), else_=0)
                ).label("failed"),
            )
            .filter(Run.created_at >= cutoff)
            .group_by(func.date(Run.created_at))
            .order_by(func.date(Run.created_at))
            .all()
        )

        return [
            {
                "date": str(r.date),
                "total": r.total,
                "failed": r.failed or 0,
                "failure_rate": round((r.failed or 0) / r.total * 100, 1) if r.total > 0 else 0,
            }
            for r in results
        ]
