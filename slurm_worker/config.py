"""
Configuration dataclasses for the worker.

Provides type-safe, immutable configuration objects with sensible defaults.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CallbackConfig:
    """Configuration for backend callbacks."""

    url: str = ""
    token: str = ""
    timeout: int = 10

    @classmethod
    def from_env(cls) -> "CallbackConfig":
        """Create config from environment variables."""
        return cls(
            url=os.environ.get("CALLBACK_URL", ""),
            token=os.environ.get("CALLBACK_TOKEN", ""),
        )

    @property
    def is_enabled(self) -> bool:
        """Check if callbacks are configured."""
        return bool(self.url and self.token)


@dataclass(frozen=True)
class PySRConfig:
    """Configuration for PySR symbolic regression."""

    niterations: int | None = None  # None = auto-estimate
    populations: int = 15
    population_size: int = 33
    ncycles_per_iteration: int = 550
    binary_operators: list[str] = field(default_factory=lambda: ["+", "-", "*", "/"])
    unary_operators: list[str] = field(default_factory=lambda: ["exp", "log", "sqrt", "abs"])
    maxsize: int = 20
    maxdepth: int = 10
    timeout_in_seconds: int = 3600
    parsimony: float = 0.0032
    turbo: bool = True
    max_scatter_points: int = 500
    scatter_seed: int = 42


@dataclass
class WorkerConfig:
    """Main worker configuration."""

    task_type: str
    run_id: str
    output_path: str
    input_path: str = ""  # Optional - if empty, fetches via HTTP
    callback: CallbackConfig = field(default_factory=CallbackConfig.from_env)
    task_key: str = ""  # Key within the run (e.g. pysr_2); defaults to task_type

    @classmethod
    def from_args(cls, args) -> "WorkerConfig":
        """Create config from parsed CLI arguments."""
        callback = CallbackConfig(
            url=args.callback_url or os.environ.get("CALLBACK_URL", ""),
            token=args.callback_token or os.environ.get("CALLBACK_TOKEN", ""),
        )
        return cls(
            task_type=args.task_type,
            run_id=args.run_id or os.environ.get("SLURM_JOB_ID", "local"),
            input_path=getattr(args, "input", "") or "",
            output_path=args.output,
            callback=callback,
            task_key=getattr(args, "task_key", "") or args.task_type,
        )
