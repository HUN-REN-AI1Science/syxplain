"""
Slurm data models.

Pydantic models for slurmrestd API request/response handling.
Compatible with slurmrestd API v0.0.41+
"""

import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobState(str, Enum):
    """Slurm job states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    NODE_FAIL = "NODE_FAIL"
    PREEMPTED = "PREEMPTED"
    BOOT_FAIL = "BOOT_FAIL"
    DEADLINE = "DEADLINE"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_slurm_state(cls, state: str) -> "JobState":
        """Convert slurmrestd state string to JobState enum."""
        state_upper = state.upper().replace(" ", "_")
        try:
            return cls(state_upper)
        except ValueError:
            return cls.UNKNOWN

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal state (job is done)."""
        return self in {
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.TIMEOUT,
            JobState.NODE_FAIL,
            JobState.PREEMPTED,
            JobState.BOOT_FAIL,
            JobState.DEADLINE,
            JobState.OUT_OF_MEMORY,
        }

    @property
    def is_success(self) -> bool:
        """Check if this is a successful terminal state."""
        return self == JobState.COMPLETED


@dataclass
class JobStatus:
    """Status information for a Slurm job."""

    job_id: str
    state: JobState
    exit_code: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    node_list: str | None = None
    reason: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_slurm_response(cls, data: dict[str, Any]) -> "JobStatus":
        """Parse slurmrestd job status response."""
        job_info = data.get("jobs", [{}])[0] if data.get("jobs") else {}

        state_str = job_info.get("job_state", "UNKNOWN")
        if isinstance(state_str, list):
            state_str = state_str[0] if state_str else "UNKNOWN"

        exit_code = None
        if "exit_code" in job_info:
            exit_info = job_info["exit_code"]
            exit_code = exit_info.get("return_code") if isinstance(exit_info, dict) else exit_info

        start_time = None
        if job_info.get("start_time"):
            with contextlib.suppress(ValueError, TypeError, OSError):
                start_time = datetime.fromtimestamp(job_info["start_time"])

        end_time = None
        if job_info.get("end_time"):
            with contextlib.suppress(ValueError, TypeError, OSError):
                end_time = datetime.fromtimestamp(job_info["end_time"])

        return cls(
            job_id=str(job_info.get("job_id", "")),
            state=JobState.from_slurm_state(state_str),
            exit_code=exit_code,
            start_time=start_time,
            end_time=end_time,
            node_list=job_info.get("nodes"),
            reason=job_info.get("state_reason"),
            raw_response=data,
        )


@dataclass
class SlurmJob:
    """Represents a submitted Slurm job."""

    job_id: str
    name: str
    partition: str
    status: JobStatus
    submitted_at: datetime = field(default_factory=datetime.utcnow)


def _parse_time_limit(time_str: str) -> int:
    """
    Parse time limit string to minutes.

    Accepts formats: "HH:MM:SS", "MM:SS", "minutes", or integer minutes.

    Args:
        time_str: Time limit string or integer

    Returns:
        Time limit in minutes
    """
    if isinstance(time_str, int):
        return time_str

    parts = str(time_str).split(":")
    if len(parts) == 3:
        # HH:MM:SS format
        hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
        return hours * 60 + minutes + (1 if seconds > 0 else 0)
    elif len(parts) == 2:
        # MM:SS format
        minutes, seconds = int(parts[0]), int(parts[1])
        return minutes + (1 if seconds > 0 else 0)
    else:
        # Just minutes
        return int(time_str)


def _parse_memory(memory_str: str) -> int:
    """
    Parse memory string to megabytes.

    Accepts formats: "16G", "16384M", "16384", or integer MB.

    Args:
        memory_str: Memory string

    Returns:
        Memory in megabytes
    """
    if isinstance(memory_str, int):
        return memory_str

    memory_str = str(memory_str).upper().strip()

    if memory_str.endswith("G"):
        return int(float(memory_str[:-1]) * 1024)
    elif memory_str.endswith("M"):
        return int(memory_str[:-1])
    elif memory_str.endswith("K"):
        return int(float(memory_str[:-1]) / 1024)
    else:
        # Assume MB
        return int(memory_str)


@dataclass
class SlurmJobSubmission:
    """
    Job submission request for slurmrestd.

    Compatible with slurmrestd API v0.0.41+ format.
    """

    script: str
    name: str
    partition: str
    cpus: int = 8
    memory: str = "16G"
    time_limit: str = "04:00:00"
    nodes: int = 1
    tasks: int = 1
    working_directory: str | None = None
    environment: dict[str, str] = field(default_factory=dict)
    stdout_path: str | None = None
    stderr_path: str | None = None
    gres: str | None = None  # GPU resources, e.g., "gpu:1"

    def to_slurm_request(self) -> dict[str, Any]:
        """
        Convert to slurmrestd API v0.0.41+ request format.

        Returns:
            Dict compatible with slurmrestd job/submit endpoint
        """
        # Parse time limit to minutes
        time_minutes = _parse_time_limit(self.time_limit)

        # Build job specification matching slurmrestd v0.0.41 format
        # Note: nodes must be a string (e.g., "1" or "1-4"), not an integer
        job_spec: dict[str, Any] = {
            "name": self.name,
            "partition": self.partition,
            "nodes": str(self.nodes),
            "tasks": self.tasks,
            "time_limit": {"set": True, "number": time_minutes},
        }

        # Memory - use memory_per_node in MB
        memory_mb = _parse_memory(self.memory)
        job_spec["memory_per_node"] = {"set": True, "number": memory_mb}

        # CPUs per task (plain integer, not wrapped object)
        if self.cpus:
            job_spec["cpus_per_task"] = self.cpus

        # Working directory
        if self.working_directory:
            job_spec["current_working_directory"] = self.working_directory

        # Environment variables
        if self.environment:
            job_spec["environment"] = self.environment

        # Output/Error paths (use 'output'/'error' not 'standard_output'/'standard_error')
        if self.stdout_path:
            job_spec["output"] = self.stdout_path

        if self.stderr_path:
            job_spec["error"] = self.stderr_path

        # GPU resources
        if self.gres:
            job_spec["tres_per_job"] = f"gres:{self.gres}"

        return {
            "job": job_spec,
            "script": self.script,
        }


@dataclass
class SlurmFileUpload:
    """File upload request for Slurm staging."""

    filename: str
    content: bytes
    job_id: str | None = None
    destination_path: str | None = None
