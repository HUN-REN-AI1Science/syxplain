"""
Progress reporter for backend communication.

Implements the Observer pattern - tasks notify the reporter of progress,
which then forwards updates to the backend API.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import requests

from slurm_worker.config import CallbackConfig
from slurm_worker.logging_config import get_logger

logger = get_logger("reporting")


class ProgressObserver(ABC):
    """Abstract base for progress observers (Interface Segregation)."""

    @abstractmethod
    def on_progress(self, progress: int, status: Optional[str], step: Optional[str]) -> None:
        """Called when progress updates."""
        pass

    @abstractmethod
    def on_error(self, error: str, details: Optional[Dict[str, Any]]) -> None:
        """Called when an error occurs."""
        pass

    @abstractmethod
    def on_complete(self, results: Dict[str, Any]) -> None:
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

    def __init__(self, run_id: str, config: Optional[CallbackConfig] = None):
        """
        Initialize progress reporter.

        Args:
            run_id: UUID of the run being processed
            config: Callback configuration (defaults to env vars)
        """
        self.run_id = run_id
        self.config = config or CallbackConfig.from_env()
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
        payload: Dict[str, Any],
        timeout: Optional[int] = None,
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
        status: Optional[str] = None,
        step: Optional[str] = None,
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

        self._make_request("progress", {
            "progress": progress,
            "status": status,
            "step_name": step,
        })

    def on_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Report error.

        Args:
            error: Error message
            details: Additional error details
        """
        logger.error(f"Error: {error}")
        self._make_request("error", {"error": error, "details": details})

    def on_complete(self, results: Dict[str, Any]) -> None:
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
        status: Optional[str] = None,
        step_name: Optional[str] = None,
    ) -> bool:
        """Alias for on_progress (backwards compatibility)."""
        self.on_progress(progress, status, step_name)
        return True

    def report_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> bool:
        """Alias for on_error (backwards compatibility)."""
        self.on_error(error, details)
        return True

    def report_completion(self, results: Dict[str, Any]) -> bool:
        """Alias for on_complete (backwards compatibility)."""
        self.on_complete(results)
        return True
