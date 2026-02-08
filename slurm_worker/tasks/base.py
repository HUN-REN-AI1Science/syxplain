"""
Base task class and result types.

Defines the interface for all task implementations (Strategy pattern)
and provides common functionality (Template Method pattern).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from slurm_worker.reporting import ProgressReporter


@dataclass
class TaskResult:
    """
    Immutable result of a task execution.

    Attributes:
        status: 'success' or 'error'
        data: Result data
        error: Error message if failed
    """

    status: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def success(cls, **data) -> "TaskResult":
        """Create a successful result."""
        return cls(status="success", data=data)

    @classmethod
    def failure(cls, error: str, **data) -> "TaskResult":
        """Create a failure result."""
        return cls(status="error", error=error, data=data)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {"status": self.status, **self.data}
        if self.error:
            result["error"] = self.error
        return result


class Task(ABC):
    """
    Abstract base class for compute tasks.

    Implements the Template Method pattern - subclasses implement
    the _execute method while the run method provides the common
    workflow with progress reporting.

    Attributes:
        name: Task type name
        reporter: Progress reporter instance
    """

    name: str = "base"

    def __init__(self, reporter: ProgressReporter):
        """
        Initialize task with progress reporter.

        Args:
            reporter: Progress reporter for status updates
        """
        self.reporter = reporter

    @abstractmethod
    def _validate_input(self, input_data: dict[str, Any]) -> None:
        """
        Validate input data.

        Args:
            input_data: Raw input data

        Raises:
            ValueError: If input is invalid
        """
        pass

    @abstractmethod
    def _execute(self, input_data: dict[str, Any]) -> TaskResult:
        """
        Execute the task.

        Args:
            input_data: Validated input data

        Returns:
            Task result
        """
        pass

    def run(self, input_data: dict[str, Any]) -> TaskResult:
        """
        Run the task with validation and error handling.

        This is the template method that defines the execution workflow.

        Args:
            input_data: Raw input data

        Returns:
            Task result
        """
        try:
            self._validate_input(input_data)
            return self._execute(input_data)
        except Exception as e:
            return TaskResult.failure(str(e))

    def _report(self, progress: int, status: str, step: str) -> None:
        """
        Convenience method for progress reporting.

        Args:
            progress: Progress percentage (0-100)
            status: Human-readable status
            step: Step identifier
        """
        self.reporter.on_progress(progress, status, step)


@dataclass
class DataFrameInput:
    """
    Parsed DataFrame input with metadata.

    Encapsulates the common input structure for tasks.
    """

    df: Any  # pandas DataFrame
    target_column: str
    predictor_columns: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataFrameInput":
        """
        Parse input dictionary into DataFrameInput.

        Args:
            data: Input dictionary with 'data', 'target_column', 'predictor_columns'

        Returns:
            Parsed DataFrameInput
        """
        import pandas as pd

        df = pd.DataFrame(**data["data"])
        return cls(
            df=df,
            target_column=data["target_column"],
            predictor_columns=data["predictor_columns"],
        )

    @property
    def n_rows(self) -> int:
        """Number of rows in the DataFrame."""
        return len(self.df)

    @property
    def n_features(self) -> int:
        """Number of predictor features."""
        return len(self.predictor_columns)

    @property
    def X(self) -> Any:
        """Predictor matrix."""
        return self.df[self.predictor_columns]

    @property
    def y(self) -> Any:
        """Target vector."""
        return self.df[self.target_column]
