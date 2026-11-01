"""
Agent activity events: which ones carry results, and trimming a long log.

Fits and search events are what a client rebuilds the leaderboard and the search panels from;
the agent's budget bounds how many a run has, so they are never dropped. Only the narration
around them (thoughts, notes, tool steps) makes room when a log grows past its limit. Used by
the SSE replay log and by the activity stored with a run's results.
"""

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

RESULT_KINDS = frozenset(
    {"fit", "search_started", "search_completed", "search_failed", "search_cancelled"}
)


def trim_narration(
    items: list[T], limit: int, kind_of: Callable[[T], Any] = lambda e: e.get("kind")
) -> list[T]:
    """``items`` with the oldest narration dropped until at most ``limit`` remain, if possible."""
    excess = len(items) - limit
    if excess <= 0:
        return list(items)
    kept = []
    for item in items:
        if excess > 0 and kind_of(item) not in RESULT_KINDS:
            excess -= 1
        else:
            kept.append(item)
    return kept
