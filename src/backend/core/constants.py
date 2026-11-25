"""
Shared constants for the Syxplain backend.
"""

from enum import Enum

# Every new run is one analysis that runs the full pipeline (agent, PySR, literature).
# Old runs keep the "quick"/"deep" they were stored with.
STANDARD_ANALYSIS = "standard"


class RunStatus(str, Enum):
    """Run lifecycle statuses. Inherits from str so comparisons with raw strings still work."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_statuses(cls) -> frozenset["RunStatus"]:
        return _TERMINAL_STATUSES

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        return status in _TERMINAL_STATUSES

    @classmethod
    def active_statuses(cls) -> frozenset["RunStatus"]:
        """Statuses of a run that has not finished yet."""
        return _ACTIVE_STATUSES


_TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.TIMEOUT, RunStatus.CANCELLED}
)
_ACTIVE_STATUSES = frozenset({RunStatus.PENDING, RunStatus.RUNNING})
