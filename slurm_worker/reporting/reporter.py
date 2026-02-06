"""
Progress reporter for backend communication.

Implements the Observer pattern - tasks notify the reporter of progress,
which then forwards updates to the backend API.
"""

from abc import ABC, abstractmethod
from typing import Any

import requests

from slurm_worker.config import CallbackConfig
from slurm_worker.logging_config import get_logger

logger = get_logger("reporting")


class ProgressObserver(ABC):
    """Abstract base for progress observers (Interface Segregation)."""

    @abstractmethod
    def on_progress(self, progress: int, status: str | None, step: str | None) -> None:
        """Called when progress updates."""
        pass

    @abstractmethod
    def on_error(self, error: str, details: dict[str, Any] | None) -> None:
        """Called when an error occurs."""
        pass

    @abstractmethod
    def on_complete(self, results: dict[str, Any]) -> None:
        """Called when task completes."""
        pass


class ProgressReporter(ProgressObserver):
    """
    Reports task progress to the backend API.

    Handles HTTP communication with graceful fallback when callbacks
    are not configured.

    Attributes:
        run_id: UUID of the run being processed
        config: Callback configuration
    """

    def __init__(self, run_id: str, config: CallbackConfig | None = None, task_type: str | None = None):
        """
        Initialize progress reporter.

        Args:
            run_id: UUID of the run being processed
            config: Callback configuration (defaults to env vars)
            task_type: Task type identifier (e.g., "shap", "pysr")
        """
        self.run_id = run_id
        self.config = config or CallbackConfig.from_env()
        self.task_type = task_type
        self._enabled = self.config.is_enabled

        if not self._enabled:
            logger.warning("Progress callbacks not configured - running without reporting")

    @property
    def enabled(self) -> bool:
        """Check if reporting is enabled."""
        return self._enabled

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an endpoint."""
        base = self.config.url.rstrip("/")
        return f"{base}/{endpoint}/{self.run_id}"

    def _make_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        timeout: int | None = None,
    ) -> bool:
        """
        Make HTTP POST request to backend.

        Args:
            endpoint: API endpoint name
            payload: JSON payload
            timeout: Request timeout (defaults to config)

        Returns:
            True if request was successful
        """
        if not self._enabled:
            return True

        try:
            response = requests.post(
                self._build_url(endpoint),
                json=payload,
                headers={"X-Worker-Token": self.config.token},
                timeout=timeout or self.config.timeout,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.Timeout:
            logger.warning(f"Request to {endpoint} timed out")
            return False
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request to {endpoint} failed: {e}")
            return False

    def on_progress(
        self,
        progress: int,
        status: str | None = None,
        step: str | None = None,
    ) -> None:
        """
        Report progress update.

        Args:
            progress: Progress percentage (0-100)
            status: Human-readable status message
            step: Current step name
        """
        message = f"Progress: {progress}%"
        if status:
            message += f" - {status}"
        if step:
            message += f" [{step}]"

        logger.info(message)

        payload = {
            "progress": progress,
            "status": status,
            "step_name": step,
        }
        if self.task_type:
            payload["task_type"] = self.task_type
        self._make_request("progress", payload)

    def on_error(self, error: str, details: dict[str, Any] | None = None) -> None:
        """
        Report error.

        Args:
            error: Error message
            details: Additional error details
        """
        logger.error(f"Error: {error}")
        self._make_request("error", {"error": error, "details": details})

    def on_complete(self, results: dict[str, Any]) -> None:
        """
        Report task completion.

        Args:
            results: Task results
        """
        logger.info("Task completed")
        self._make_request("complete", {"results": results}, timeout=30)

    # Convenience methods for compatibility
    def report_progress(
        self,
        progress: int,
        status: str | None = None,
        step_name: str | None = None,
    ) -> bool:
        """Alias for on_progress (backwards compatibility)."""
        self.on_progress(progress, status, step_name)
        return True

    def report_error(self, error: str, details: dict[str, Any] | None = None) -> bool:
        """Alias for on_error (backwards compatibility)."""
        self.on_error(error, details)
        return True

    def report_completion(self, results: dict[str, Any]) -> bool:
        """Alias for on_complete (backwards compatibility)."""
        self.on_complete(results)
        return True
