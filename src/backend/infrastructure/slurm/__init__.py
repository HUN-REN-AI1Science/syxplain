"""
Slurm infrastructure module.

Provides the Slurm compute backend for executing tasks on the cluster.
"""

from backend.infrastructure.slurm.backend import (
    JobNotCompletedError,
    JobNotFoundError,
    SlurmBackend,
    SlurmBackendError,
    clear_backend_cache,
    get_slurm_backend,
)
from backend.infrastructure.slurm.client import SlurmClient
from backend.infrastructure.slurm.models import (
    JobState,
    JobStatus,
    SlurmJobSubmission,
    SlurmTask,
    TaskInput,
    TaskResult,
)

__all__ = [
    "JobNotCompletedError",
    "JobNotFoundError",
    "JobState",
    "JobStatus",
    "SlurmBackend",
    "SlurmBackendError",
    "SlurmClient",
    "SlurmJobSubmission",
    "SlurmTask",
    "TaskInput",
    "TaskResult",
    "clear_backend_cache",
    "get_slurm_backend",
]
