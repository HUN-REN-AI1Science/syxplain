"""
Syxplain Slurm Worker Package.

A modular, extensible worker for executing compute tasks on Slurm clusters.
Follows SOLID principles and clean architecture patterns.

Package Structure:
    - cli: Command-line interface
    - config: Configuration dataclasses
    - tasks: Task implementations (Strategy pattern)
    - reporting: Progress reporting to backend
    - io: File I/O operations
"""

__version__ = "3.2.0"  # 3.x: keyed tasks (--task-key), guesses, target transforms; 3.1: templates; 3.2: live search progress

from slurm_worker.tasks import TaskRegistry

__all__ = ["TaskRegistry", "__version__"]
