"""
Syxplain Slurm Worker Package.

A modular, extensible worker for executing compute tasks on Slurm clusters.
Follows SOLID principles and clean architecture patterns.

Package Structure:
    - cli: Command-line interface
    - config: Configuration dataclasses
    - tasks: Task implementations (Strategy pattern)
    - reporting: Progress reporting to backend
    - visualization: Plot generation
    - io: File I/O operations
"""

__version__ = "2.0.0"

from slurm_worker.tasks import TaskRegistry

__all__ = ["TaskRegistry", "__version__"]
