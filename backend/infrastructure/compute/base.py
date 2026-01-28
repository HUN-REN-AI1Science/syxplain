"""
Compute backend base classes and interfaces.

Defines the abstract interface for compute backends that can execute
SHAP and PySR tasks either locally or on remote clusters.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class TaskState(str, Enum):
    """State of a compute task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
            TaskState.TIMEOUT,
        }

    @property
    def is_success(self) -> bool:
        """Check if this is a successful terminal state."""
        return self == TaskState.COMPLETED


@dataclass
class ComputeTaskInput:
    """
    Input specification for a compute task.

    Contains all information needed to execute a task on any backend.
    """
    task_type: str  # "shap" or "pysr"
    run_id: str  # Associated run ID for progress tracking
    input_data: Dict[str, Any]  # Serialized task input
    callback_url: Optional[str] = None  # URL for progress updates
    callback_token: Optional[str] = None  # Auth token for callbacks
    resources: Dict[str, Any] = field(default_factory=dict)  # cpus, memory, time_limit


@dataclass
class TaskStatus:
    """Status of a compute task."""
    job_id: str
    state: TaskState
    progress: int = 0  # 0-100
    message: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ComputeJob:
    """
    Represents a submitted compute job.

    Tracks the job throughout its lifecycle.
    """
    job_id: str
    task_type: str
    run_id: str
    backend: str  # "local" or "slurm"
    status: TaskStatus
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ComputeBackend(ABC):
    """
    Abstract base class for compute backends.

    Implementations handle the details of running tasks on different
    infrastructure (local processes, Slurm clusters, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name (e.g., 'local', 'slurm')."""
        pass

    @abstractmethod
    async def submit_task(self, task: ComputeTaskInput) -> ComputeJob:
        """
        Submit a task for execution.

        Args:
            task: Task specification with input data and requirements

        Returns:
            ComputeJob with job_id and initial status

        Raises:
            ComputeBackendError: If submission fails
        """
        pass

    @abstractmethod
    async def get_task_status(self, job_id: str) -> TaskStatus:
        """
        Get current status of a task.

        Args:
            job_id: Job identifier from submit_task

        Returns:
            Current TaskStatus

        Raises:
            JobNotFoundError: If job doesn't exist
            ComputeBackendError: For other errors
        """
        pass

    @abstractmethod
    async def get_task_result(self, job_id: str) -> Dict[str, Any]:
        """
        Get results of a completed task.

        Args:
            job_id: Job identifier from submit_task

        Returns:
            Task results as dictionary

        Raises:
            JobNotFoundError: If job doesn't exist
            JobNotCompletedError: If job hasn't completed successfully
            ComputeBackendError: For other errors
        """
        pass

    @abstractmethod
    async def cancel_task(self, job_id: str) -> bool:
        """
        Cancel a running task.

        Args:
            job_id: Job identifier from submit_task

        Returns:
            True if cancellation was successful

        Raises:
            ComputeBackendError: If cancellation fails
        """
        pass

    async def wait_for_completion(
        self,
        job_id: str,
        poll_interval: float = 5.0,
        timeout: Optional[float] = None,
    ) -> TaskStatus:
        """
        Wait for a task to complete.

        Default implementation polls get_task_status.
        Backends may override with more efficient implementations.

        Args:
            job_id: Job identifier
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Final TaskStatus

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        import asyncio

        elapsed = 0.0
        while True:
            status = await self.get_task_status(job_id)
            if status.state.is_terminal:
                return status

            if timeout and elapsed >= timeout:
                raise asyncio.TimeoutError(f"Task {job_id} did not complete in time")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval


class ComputeBackendError(Exception):
    """Base exception for compute backend errors."""
    pass


class JobNotFoundError(ComputeBackendError):
    """Job not found in backend."""
    pass


class JobNotCompletedError(ComputeBackendError):
    """Job has not completed successfully."""
    pass
