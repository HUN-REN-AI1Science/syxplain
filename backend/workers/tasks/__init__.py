"""
Compute task definitions module.

Provides task abstractions for SHAP and PySR computations
that can be serialized and executed on different backends.
"""

from backend.workers.tasks.base import ComputeTask, TaskType
from backend.workers.tasks.pysr_task import PySRTask
from backend.workers.tasks.shap_task import SHAPTask

__all__ = [
    "ComputeTask",
    "PySRTask",
    "SHAPTask",
    "TaskType",
]
