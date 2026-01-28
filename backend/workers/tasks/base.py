"""
Base class for compute tasks.

Defines the interface for tasks that can be serialized and executed
on different compute backends (local or Slurm).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Generic, TypeVar

import pandas as pd


class TaskType(str, Enum):
    """Types of compute tasks."""
    SHAP = "shap"
    PYSR = "pysr"


# Input and output type variables
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


@dataclass
class TaskInput:
    """Base class for task inputs."""
    pass


@dataclass
class TaskOutput:
    """Base class for task outputs."""
    pass


class ComputeTask(ABC, Generic[TInput, TOutput]):
    """
    Abstract base class for compute tasks.

    Tasks define how to serialize inputs, deserialize outputs, and
    generate worker scripts for execution on Slurm.
    """

    @property
    @abstractmethod
    def task_type(self) -> TaskType:
        """Return the task type identifier."""
        pass

    @abstractmethod
    def validate_input(self, input_data: TInput) -> None:
        """
        Validate input data before execution.

        Args:
            input_data: Task-specific input data

        Raises:
            ValueError: If input is invalid
        """
        pass

    @abstractmethod
    def serialize_input(self, input_data: TInput) -> Dict[str, Any]:
        """
        Serialize input data for transfer to worker.

        Must produce JSON-serializable output.

        Args:
            input_data: Task-specific input data

        Returns:
            Dictionary that can be serialized to JSON
        """
        pass

    @abstractmethod
    def deserialize_output(self, data: Dict[str, Any]) -> TOutput:
        """
        Deserialize output data from worker.

        Args:
            data: Dictionary from worker output JSON

        Returns:
            Task-specific output data
        """
        pass

    def serialize_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Serialize a DataFrame for JSON transport.

        Args:
            df: DataFrame to serialize

        Returns:
            Dictionary representation
        """
        # Use orient='split' for efficient serialization with type preservation
        return df.to_dict(orient="split")

    def deserialize_dataframe(self, data: Dict[str, Any]) -> pd.DataFrame:
        """
        Deserialize a DataFrame from JSON transport format.

        Args:
            data: Dictionary from serialize_dataframe

        Returns:
            Reconstructed DataFrame
        """
        return pd.DataFrame(**data)

    def generate_worker_script(
        self,
        input_path: str,
        output_path: str,
        callback_url: str = "",
        callback_token: str = "",
    ) -> str:
        """
        Generate a worker script for Slurm execution.

        Default implementation uses the syxplain_worker module.
        Subclasses can override for custom behavior.

        Args:
            input_path: Path to input JSON on Slurm
            output_path: Path for output JSON
            callback_url: URL for progress callbacks
            callback_token: Auth token for callbacks

        Returns:
            Bash script content
        """
        env_lines = []
        if callback_url:
            env_lines.append(f'export CALLBACK_URL="{callback_url}"')
        if callback_token:
            env_lines.append(f'export CALLBACK_TOKEN="{callback_token}"')

        env_section = "\n".join(env_lines) if env_lines else "# No callbacks configured"

        return f"""#!/bin/bash
set -e

# Environment setup
{env_section}

# Activate conda environment if available
if command -v conda &> /dev/null; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate syxplain_worker 2>/dev/null || true
fi

# Execute task
python -m syxplain_worker \\
    --task-type {self.task_type.value} \\
    --input "{input_path}" \\
    --output "{output_path}"
"""
