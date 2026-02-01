"""
Slurm REST API client.

Provides async interface for interacting with slurmrestd API for job submission,
file staging, and status monitoring.

Compatible with slurmrestd API v0.0.41+
"""

import asyncio
import base64
import logging

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


class SlurmFileTransferError(SlurmClientError):
    """Error during file upload/download."""

    pass


class SlurmJobNotFoundError(SlurmClientError):
    """Job not found in Slurm."""

    pass


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
        logger.debug(f"Job submission payload: {payload}")

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

    async def upload_file(
        self,
        job_id: str,
        filename: str,
        content: bytes,
        destination_dir: str | None = None,
    ) -> str:
        """
        Upload a file to Slurm staging area via slurmrestd.

        Args:
            job_id: Associated job ID (for organization)
            filename: Name of the file
            content: File content as bytes
            destination_dir: Target directory (defaults to staging area)

        Returns:
            Full path to the uploaded file

        Raises:
            SlurmFileTransferError: If upload fails
        """
        client = await self._get_client()
        settings = get_slurm_settings()

        # Organize files by job_id in staging directory
        dest_dir = destination_dir or f"{settings.staging_dir}/{job_id}"
        dest_path = f"{dest_dir}/{filename}"

        # Base64 encode the content for JSON transport
        encoded_content = base64.b64encode(content).decode("utf-8")

        payload = {
            "path": dest_path,
            "data": encoded_content,
            "encoding": "base64",
        }

        logger.info(f"Uploading file to Slurm: {dest_path}")

        try:
            response = await client.put(self._api_path("file"), json=payload)
            response.raise_for_status()
            logger.info(f"File uploaded successfully: {dest_path}")
            return dest_path

        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.json()
            except Exception:
                error_detail = e.response.text
            raise SlurmFileTransferError(
                f"File upload failed: {e.response.status_code} - {error_detail}"
            ) from e
        except httpx.RequestError as e:
            raise SlurmFileTransferError(f"Request failed: {e}") from e

    async def download_file(self, file_path: str) -> bytes:
        """
        Download a file from Slurm via slurmrestd.

        Args:
            file_path: Full path to the file on Slurm

        Returns:
            File content as bytes

        Raises:
            SlurmFileTransferError: If download fails
        """
        client = await self._get_client()

        logger.info(f"Downloading file from Slurm: {file_path}")

        try:
            response = await client.get(
                self._api_path("file"),
                params={"path": file_path},
            )
            response.raise_for_status()
            data = response.json()

            # Decode base64 content
            encoded_content = data.get("data", "")
            content = base64.b64decode(encoded_content)

            logger.info(f"File downloaded successfully: {file_path} ({len(content)} bytes)")
            return content

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise SlurmFileTransferError(f"File not found: {file_path}") from e
            raise SlurmFileTransferError(f"File download failed: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise SlurmFileTransferError(f"Request failed: {e}") from e

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: int | None = None,
        timeout: float | None = None,
    ) -> JobStatus:
        """
        Wait for a job to reach terminal state.

        Args:
            job_id: Slurm job ID
            poll_interval: Seconds between status checks (defaults to config)
            timeout: Maximum seconds to wait (None for no timeout)

        Returns:
            Final JobStatus

        Raises:
            asyncio.TimeoutError: If timeout exceeded
            SlurmClientError: For other errors
        """
        compute_settings = get_compute_settings()
        interval = poll_interval or compute_settings.job_poll_interval
        elapsed = 0.0

        while True:
            status = await self.get_job_status(job_id)

            if status.state.is_terminal:
                logger.info(f"Job {job_id} completed with state: {status.state.value}")
                return status

            logger.debug(f"Job {job_id} still {status.state.value}, waiting...")

            if timeout and elapsed >= timeout:
                raise asyncio.TimeoutError(f"Job {job_id} did not complete within {timeout}s")

            await asyncio.sleep(interval)
            elapsed += interval
