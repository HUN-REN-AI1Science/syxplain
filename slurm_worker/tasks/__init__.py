"""
Task implementations module.

Uses the Strategy pattern for different task types and
Factory pattern for task creation.
"""
from slurm_worker.tasks.base import Task, TaskResult
from slurm_worker.tasks.registry import TaskRegistry

# Register built-in tasks
from slurm_worker.tasks import shap_task  # noqa: F401
from slurm_worker.tasks import pysr_task  # noqa: F401

__all__ = ["Task", "TaskResult", "TaskRegistry"]
