"""
System monitor service for health checks and Slurm cluster status.

Provides real-time system health information for the admin dashboard.
"""

import contextlib
import logging
import time
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import get_settings, get_slurm_settings
from backend.infrastructure.database.models import Run
from backend.infrastructure.llm.client import literature_available

logger = logging.getLogger(__name__)

# Track application start time
_app_start_time = time.time()


class SystemMonitorService:
    """
    Service for system health monitoring.

    Handles health checks for database, Slurm, and other services.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def get_health_status(self) -> dict:
        """
        Get overall system health status.

        Returns:
            Dictionary with health indicators:
            - database_connected: Database connection status
            - slurm_configured: Whether Slurm credentials are configured
            - slurm_connected: Slurm API connection status
            - api_healthy: Overall API health
            - uptime_seconds: Application uptime
            - checked_at: Timestamp of health check
        """
        slurm_configured = self._is_slurm_configured()
        slurm_connected = self._check_slurm_sync() if slurm_configured else False

        database_connected = self._check_database()

        health = {
            "database_connected": database_connected,
            "slurm_configured": slurm_configured,
            "slurm_connected": slurm_connected,
            "slurm_host": self._slurm_host(),
            "api_healthy": database_connected,  # API is healthy if database works
            "uptime_seconds": int(time.time() - _app_start_time),
            "checked_at": datetime.utcnow().isoformat(),
        }

        return health

    def _check_database(self) -> bool:
        """Check database connection."""
        try:
            self.db.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def _is_slurm_configured(self) -> bool:
        """Check if Slurm is properly configured."""
        try:
            slurm_settings = get_slurm_settings()
            return slurm_settings.is_configured
        except Exception:
            return False

    def _slurm_host(self) -> str | None:
        """Hostname of the configured slurmrestd API, for display."""
        try:
            return self._url_host(get_slurm_settings().api_url)
        except Exception:
            return None

    def _check_slurm_sync(self) -> bool:
        """
        Synchronously check Slurm connection.

        Note: This is a sync wrapper that creates a new event loop
        for the async Slurm client check.
        """
        try:
            slurm_settings = get_slurm_settings()
            if not slurm_settings.api_url or not slurm_settings.auth_token:
                return False

            # Simple HTTP check using httpx sync client
            import httpx

            response = httpx.get(
                f"{slurm_settings.api_url}/slurm/v0.0.41/diag",
                headers={
                    "Authorization": f"Bearer {slurm_settings.auth_token}",
                    "Slurm-User-Name": slurm_settings.user_name,
                },
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Slurm health check failed: {e}")
            return False

    def get_slurm_status(self) -> dict | None:
        """
        Get Slurm cluster status.

        Returns:
            Dictionary with Slurm cluster info or None if not available:
            - cluster_name: Name of the cluster
            - cluster_status: Overall cluster status
            - partitions: List of partition info
            - queue_length: Number of jobs in queue
            - active_jobs: Number of running jobs
            - nodes: Node status summary
        """
        if not self._is_slurm_configured():
            return None

        try:
            slurm_settings = get_slurm_settings()
            import httpx

            # Get cluster info
            diag_response = httpx.get(
                f"{slurm_settings.api_url}/slurm/v0.0.41/diag",
                headers={
                    "Authorization": f"Bearer {slurm_settings.auth_token}",
                    "Slurm-User-Name": slurm_settings.user_name,
                },
                timeout=10.0,
            )

            if diag_response.status_code != 200:
                return {"error": "Failed to get Slurm diagnostics"}

            diag_response.json()

            # Get jobs info
            jobs_response = httpx.get(
                f"{slurm_settings.api_url}/slurm/v0.0.41/jobs",
                headers={
                    "Authorization": f"Bearer {slurm_settings.auth_token}",
                    "Slurm-User-Name": slurm_settings.user_name,
                },
                timeout=10.0,
            )

            jobs_data = jobs_response.json() if jobs_response.status_code == 200 else {}
            jobs = jobs_data.get("jobs", [])

            # Get partitions info
            partitions_response = httpx.get(
                f"{slurm_settings.api_url}/slurm/v0.0.41/partitions",
                headers={
                    "Authorization": f"Bearer {slurm_settings.auth_token}",
                    "Slurm-User-Name": slurm_settings.user_name,
                },
                timeout=10.0,
            )

            partitions_data = (
                partitions_response.json() if partitions_response.status_code == 200 else {}
            )
            partitions = partitions_data.get("partitions", [])

            # Get nodes info
            nodes_response = httpx.get(
                f"{slurm_settings.api_url}/slurm/v0.0.41/nodes",
                headers={
                    "Authorization": f"Bearer {slurm_settings.auth_token}",
                    "Slurm-User-Name": slurm_settings.user_name,
                },
                timeout=10.0,
            )

            nodes_data = nodes_response.json() if nodes_response.status_code == 200 else {}
            nodes = nodes_data.get("nodes", [])

            # Aggregate job counts
            running_jobs = sum(1 for j in jobs if j.get("job_state", [""])[0] == "RUNNING")
            pending_jobs = sum(1 for j in jobs if j.get("job_state", [""])[0] == "PENDING")

            # Aggregate node status
            node_status = {}
            for node in nodes:
                state = (
                    node.get("state", ["UNKNOWN"])[0]
                    if isinstance(node.get("state"), list)
                    else node.get("state", "UNKNOWN")
                )
                node_status[state] = node_status.get(state, 0) + 1

            # Build partition summary
            # SLURM API structure:
            # - name: partition name
            # - partition.state: array like ["UP"]
            # - nodes.total: total nodes
            # - cpus.total: total CPUs
            partition_summary = []
            for part in partitions:
                # Extract state from nested structure
                state = "UNKNOWN"
                if "partition" in part and "state" in part["partition"]:
                    state_list = part["partition"]["state"]
                    state = state_list[0] if state_list else "UNKNOWN"

                # Extract nodes and CPUs from nested structure
                total_nodes = part.get("nodes", {}).get("total", 0)
                total_cpus = part.get("cpus", {}).get("total", 0)

                partition_summary.append(
                    {
                        "name": part.get("name", "unknown"),
                        "state": state,
                        "total_nodes": total_nodes,
                        "total_cpus": total_cpus,
                    }
                )

            return {
                "cluster_status": "healthy" if running_jobs >= 0 else "degraded",
                "queue_length": pending_jobs,
                "active_jobs": running_jobs,
                "total_jobs": len(jobs),
                "partitions": partition_summary,
                "node_status": node_status,
                "total_nodes": len(nodes),
                "checked_at": datetime.utcnow().isoformat(),
                # Configuration info for highlighting in UI
                "configured_partition": slurm_settings.partition,
                "configured_cpus": slurm_settings.cpus,
                "configured_memory": slurm_settings.memory,
            }

        except Exception as e:
            logger.error(f"Failed to get Slurm status: {e}")
            return {"error": str(e)}

    def get_database_stats(self) -> dict:
        """
        Get database statistics.

        Returns:
            Dictionary with database info
        """
        try:
            # Get table counts
            run_count = self.db.query(Run).count()

            return {
                "run_count": run_count,
                "connection_pool_size": "default",
                "status": "healthy",
            }
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {"status": "error", "error": str(e)}

    def _mask_secret(self, secret: str | None, visible_chars: int = 4) -> str | None:
        """
        Mask a secret value, showing only the last few characters.

        Args:
            secret: The secret value to mask
            visible_chars: Number of characters to show at the end

        Returns:
            Masked string like '***abc1' or None if secret is empty
        """
        if not secret:
            return None
        if len(secret) <= visible_chars:
            return "***"
        return f"***{secret[-visible_chars:]}"

    @staticmethod
    def _url_host(url: str | None) -> str | None:
        """Hostname from a URL (no credentials or port), or None if empty or invalid."""
        if not url:
            return None
        try:
            return urlparse(url).hostname
        except ValueError:
            return None

    def get_config_summary(self) -> dict:
        """
        Get sanitized configuration summary.

        Returns:
            Dictionary with non-secret configuration values and masked secrets
        """
        settings = self.settings

        # Get slurm settings for masked secrets
        slurm_settings = None
        with contextlib.suppress(Exception):
            slurm_settings = get_slurm_settings()

        # Build sanitized config - Slurm is the only supported backend
        config = {
            "compute_backend": "slurm",
            "analysis_timeout_hours": 2.0,  # Default or from config
            "max_file_size_mb": 50,  # Default or from config
            "rate_limits": {
                "runs_per_minute": 10,
                "uploads_per_minute": 20,
                "admin_requests_per_minute": 30,
            },
            "features": {
                "slurm_configured": self._is_slurm_configured(),
                "slurm_host": self._slurm_host(),
                "literature_search_enabled": literature_available(None),
                "user_api_keys_enabled": True,
            },
            "secrets": {
                "openai_api_key": self._mask_secret(settings.llm.openai_api_key),
                "slurm_auth_token": self._mask_secret(
                    slurm_settings.auth_token if slurm_settings else None
                ),
                "database_host": self._url_host(settings.database.url),
            },
        }

        return config
