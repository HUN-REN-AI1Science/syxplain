"""
Compute backend infrastructure module.

Provides abstraction layer for the Slurm compute backend.
"""

from backend.infrastructure.compute.base import (
    ComputeBackend,
    ComputeJob,
    ComputeTaskInput,
    TaskState,
    TaskStatus,
)
from backend.infrastructure.compute.factory import get_compute_backend

__all__ = [
    "ComputeBackend",
    "ComputeJob",
    "ComputeTaskInput",
    "TaskState",
    "TaskStatus",
    "get_compute_backend",
]
