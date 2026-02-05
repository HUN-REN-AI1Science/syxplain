"""
Slurm REST API client.

Provides async interface for interacting with slurmrestd API for job submission
and status monitoring.

Compatible with slurmrestd API v0.0.41+
"""

import asyncio
import json
import logging
from collections.abc import Callable

import httpx

from backend.core.config import get_compute_settings, get_slurm_settings
from backend.infrastructure.slurm.models import (
    JobStatus,
    SlurmJobSubmission,
)

logger = logging.getLogger(__name__)

# Slurm REST API version - hardcoded, change here if needed
API_VERSION = "v0.0.41"


class SlurmClientError(Exception):
    """Base exception for Slurm client errors."""

    pass


class SlurmJobSubmissionError(SlurmClientError):
    """Error during job submission."""

    pass


class SlurmJobNotFoundError(SlurmClientError):
    """Job not found in Slurm."""

    pass


def is_quota_error(error: SlurmJobSubmissionError) -> bool:
    """
    Check if error is a quota/QOS policy violation.

    These errors occur when the user has reached their job submission limit
    or other QOS policy restrictions. They are transient and can be retried.

    Args:
        error: The submission error to check

    Returns:
        True if this is a quota/QOS error that should be retried
    """
    error_str = str(error).lower()
    return (
        "qos policy" in error_str
        or '"error_number": 2050' in error_str
        or "error_number\": 2050" in error_str
        or "job submit limit" in error_str
    )


class SlurmClient:
    """
    Async client for slurmrestd API.

    Handles job submission, file staging, status monitoring, and job cancellation.
    Compatible with modern slurmrestd API (v0.0.41+).

    Usage:
        client = SlurmClient()
        job_id = await client.submit_job(submission)
        status = await client.get_job_status(job_id)
        await client.cancel_job(job_id)
    """

    def __init__(
        self,
        base_url: str | None = None,
        auth_token: str | None = None,
        user_name: str | None = None,
        timeout: float = 60.0,
    ):
        """
        Initialize Slurm client.

        Args:
            base_url: slurmrestd API base URL (defaults to config)
            auth_token: JWT authentication token (defaults to config)
            user_name: Slurm username for job submission (defaults to config)
            timeout: Request timeout in seconds
        """
        settings = get_slurm_settings()
        self.base_url = (base_url or settings.api_url).rstrip("/")
        self.auth_token = auth_token or settings.auth_token
        self.user_name = user_name or settings.user_name
        self.timeout = timeout

        if not self.base_url:
            raise SlurmClientError("Slurm API URL not configured")
        if not self.auth_token:
            raise SlurmClientError("Slurm auth token not configured")

        self._client: httpx.AsyncClient | None = None

    def _get_headers(self) -> dict[str, str]:
        """Build request headers for slurmrestd API."""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "Slurm-User-Name": self.user_name,
        }

    def _api_path(self, endpoint: str) -> str:
        """Build full API path with version."""
        return f"/slurm/{API_VERSION}/{endpoint}"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "SlurmClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def submit_job(self, submission: SlurmJobSubmission) -> str:
        """
        Submit a job to Slurm.

        Args:
            submission: Job submission details

        Returns:
            Slurm job ID as string

        Raises:
            SlurmJobSubmissionError: If submission fails
        """
        client = await self._get_client()
        payload = submission.to_slurm_request()

        logger.info(f"Submitting job '{submission.name}' to partition '{submission.partition}'")
        logger.info(f"Job submission payload:\n{json.dumps(payload, indent=2)}")

        try:
            response = await client.post(self._api_path("job/submit"), json=payload)
            response.raise_for_status()
            data = response.json()

            job_id = data.get("job_id")
            if not job_id:
                raise SlurmJobSubmissionError(f"No job_id in response: {data}")

            logger.info(f"Job submitted successfully: {job_id}")
            return str(job_id)

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.json()
            except Exception:
                error_detail = e.response.text
            raise SlurmJobSubmissionError(
                f"Job submission failed: {e.response.status_code} - {error_detail}"
            ) from e
        except httpx.RequestError as e:
            raise SlurmJobSubmissionError(f"Request failed: {e}") from e

    async def get_job_status(self, job_id: str) -> JobStatus:
        """
        Get status of a Slurm job.

        Args:
            job_id: Slurm job ID

        Returns:
            JobStatus with current state

        Raises:
            SlurmJobNotFoundError: If job not found
            SlurmClientError: For other errors
        """
        client = await self._get_client()

        try:
            response = await client.get(self._api_path(f"job/{job_id}"))
            response.raise_for_status()
            data = response.json()

            if not data.get("jobs"):
                raise SlurmJobNotFoundError(f"Job {job_id} not found")

            return JobStatus.from_slurm_response(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SlurmJobNotFoundError(f"Job {job_id} not found") from e
            raise SlurmClientError(f"Failed to get job status: {e}") from e
        except httpx.RequestError as e:
            raise SlurmClientError(f"Request failed: {e}") from e

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a Slurm job.

        Args:
            job_id: Slurm job ID

        Returns:
            True if cancellation was accepted

        Raises:
            SlurmClientError: If cancellation fails
        """
        client = await self._get_client()

        try:
            response = await client.delete(self._api_path(f"job/{job_id}"))
            response.raise_for_status()
            logger.info(f"Job {job_id} cancellation requested")
            return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Job {job_id} not found for cancellation")
                return False
            raise SlurmClientError(f"Failed to cancel job: {e}") from e
        except httpx.RequestError as e:
            raise SlurmClientError(f"Request failed: {e}") from e

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: int | None = None,
        timeout: float | None = None,
        on_state_change: Callable | None = None,
    ) -> JobStatus:
        """
        Wait for a job to reach terminal state.

        Args:
            job_id: Slurm job ID
            poll_interval: Seconds between status checks (defaults to config)
            timeout: Maximum seconds to wait (None for no timeout)
            on_state_change: Optional callback called when job state changes.
                             Signature: on_state_change(old_state, new_state, status)

        Returns:
            Final JobStatus

        Raises:
            asyncio.TimeoutError: If timeout exceeded
            SlurmClientError: For other errors
        """
        from backend.infrastructure.slurm.models import JobState

        compute_settings = get_compute_settings()
        interval = poll_interval or compute_settings.job_poll_interval
        elapsed = 0.0
        poll_count = 0
        last_state: JobState | None = None

        while True:
            status = await self.get_job_status(job_id)

            # Notify on state change
            if on_state_change and status.state != last_state:
                try:
                    on_state_change(last_state, status.state, status)
                except Exception as e:
                    logger.warning(f"State change callback error: {e}")
                last_state = status.state

            if status.state.is_terminal:
                logger.info(f"Job {job_id} completed with state: {status.state.value}")
                return status

            # Rate-limit polling debug logs (every ~2 min at 10s intervals)
            poll_count += 1
            if poll_count % 12 == 0:
                logger.debug(
                    f"Job {job_id} still {status.state.value}, waited {int(elapsed)}s"
                )

            if timeout and elapsed >= timeout:
                raise asyncio.TimeoutError(f"Job {job_id} did not complete within {timeout}s")

            await asyncio.sleep(interval)
            elapsed += interval
