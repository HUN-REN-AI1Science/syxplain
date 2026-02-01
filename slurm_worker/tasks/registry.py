"""
Task registry implementing the Factory pattern.

Provides centralized task creation and registration,
following the Open/Closed principle - new tasks can be
added without modifying existing code.
"""

from collections.abc import Callable

from slurm_worker.reporting import ProgressReporter
from slurm_worker.tasks.base import Task


class TaskRegistry:
    """
    Registry for task types (Factory pattern).

    Allows registration and creation of task instances by name.
    Supports both class registration and factory function registration.
    """

    _tasks: dict[str, type[Task]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[type[Task]], type[Task]]:
        """
        Decorator to register a task class.

        Usage:
            @TaskRegistry.register("my_task")
            class MyTask(Task):
                ...

        Args:
            name: Task type name

        Returns:
            Decorator function
        """

        def decorator(task_cls: type[Task]) -> type[Task]:
            cls._tasks[name] = task_cls
            task_cls.name = name
            return task_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[Task]:
        """
        Get task class by name.

        Args:
            name: Task type name

        Returns:
            Task class

        Raises:
            KeyError: If task type not registered
        """
        if name not in cls._tasks:
            available = ", ".join(cls._tasks.keys())
            raise KeyError(f"Unknown task type: {name}. Available: {available}")
        return cls._tasks[name]

    @classmethod
    def create(cls, name: str, reporter: ProgressReporter) -> Task:
        """
        Create task instance by name.

        Args:
            name: Task type name
            reporter: Progress reporter

        Returns:
            Task instance
        """
        task_cls = cls.get(name)
        return task_cls(reporter)

    @classmethod
    def available_tasks(cls) -> list:
        """Get list of registered task names."""
        return list(cls._tasks.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a task type is registered."""
        return name in cls._tasks
