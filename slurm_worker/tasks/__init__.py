"""
Task implementations module.

Uses the Strategy pattern for different task types and
Factory pattern for task creation.
"""

# Register built-in tasks
from slurm_worker.tasks import (
    pysr_task,  # noqa: F401
    shap_task,  # noqa: F401
)
from slurm_worker.tasks.base import Task, TaskResult
from slurm_worker.tasks.registry import TaskRegistry

__all__ = ["Task", "TaskRegistry", "TaskResult"]
