"""
SSE connection manager for real-time progress updates.

Manages asyncio.Queue instances per SSE client and broadcasts progress updates
to all connected clients watching a specific run.
"""

import asyncio
import contextlib
import logging
from collections import OrderedDict, defaultdict
from typing import Any

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "failed", "timeout", "cancelled")
MAX_QUEUE_SIZE = 256
MAX_SSE_CONNECTIONS_PER_USER = 5
MAX_RECENT_EVENTS = 300
MAX_REPLAY_RUNS = 200
# Events a rejoining client rebuilds its leaderboard and search panels from. The agent's
# budget bounds how many a run has, so they are never evicted: only the narration around
# them (thoughts, notes, tool steps) makes room once a run has MAX_RECENT_EVENTS events.
RESULT_KINDS = frozenset(
    {"fit", "search_started", "search_completed", "search_failed", "search_cancelled"}
)


def _trim_replay(recent: list[dict[str, Any]]) -> None:
    """Drop the oldest narration events until the log fits MAX_RECENT_EVENTS again."""
    excess = len(recent) - MAX_RECENT_EVENTS
    if excess <= 0:
        return
    kept = []
    for message in recent:
        if excess > 0 and message["event"].get("kind") not in RESULT_KINDS:
            excess -= 1
        else:
            kept.append(message)
    recent[:] = kept


class SSEConnectionManager:
    """
    Singleton manager for SSE connections.

    Each connected client gets an asyncio.Queue. Broadcasting pushes
    messages to all queues for a given run_id.
    """

    _instance: "SSEConnectionManager | None" = None

    def __new__(cls) -> "SSEConnectionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._queues = defaultdict(set)
            cls._instance._user_queues = defaultdict(set)
            cls._instance._recent_events = OrderedDict()
            cls._instance._search_progress = OrderedDict()
        return cls._instance

    @property
    def _queues(self) -> dict[str, set[asyncio.Queue]]:
        """Queues indexed by run_id."""
        return self.__dict__.get("_queues_store", defaultdict(set))

    @_queues.setter
    def _queues(self, value: dict[str, set[asyncio.Queue]]) -> None:
        self.__dict__["_queues_store"] = value

    @property
    def _user_queues(self) -> dict[str, set[tuple[str, asyncio.Queue]]]:
        """Queues indexed by user_id, storing (run_id, queue) tuples."""
        return self.__dict__.get("_user_queues_store", defaultdict(set))

    @_user_queues.setter
    def _user_queues(self, value: dict[str, set[tuple[str, asyncio.Queue]]]) -> None:
        self.__dict__["_user_queues_store"] = value

    def connect(self, run_id: str, user_id: str) -> asyncio.Queue:
        """
        Register a new SSE client for a run.

        Args:
            run_id: UUID of the run being watched
            user_id: UUID of the authenticated user

        Returns:
            An asyncio.Queue that will receive progress dicts.

        Raises:
            ConnectionError: If the user has reached the max SSE connection limit.
        """
        # Enforce per-user connection limit
        if len(self._user_queues.get(user_id, set())) >= MAX_SSE_CONNECTIONS_PER_USER:
            logger.warning(
                f"SSE connection limit reached for user {user_id[:8]}... "
                f"(max {MAX_SSE_CONNECTIONS_PER_USER})"
            )
            raise ConnectionError(
                f"Maximum {MAX_SSE_CONNECTIONS_PER_USER} concurrent SSE connections per user"
            )

        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._queues[run_id].add(queue)
        self._user_queues[user_id].add((run_id, queue))
        logger.info(
            f"SSE connected: user={user_id[:8]}... run={run_id[:8]}... "
            f"(total connections for run: {len(self._queues[run_id])})"
        )
        return queue

    def disconnect(self, queue: asyncio.Queue, run_id: str, user_id: str) -> None:
        """
        Remove an SSE client queue.

        Args:
            queue: The asyncio.Queue to remove
            run_id: UUID of the run being watched
            user_id: UUID of the authenticated user
        """
        self._queues[run_id].discard(queue)
        self._user_queues[user_id].discard((run_id, queue))

        # Clean up empty sets
        if not self._queues[run_id]:
            del self._queues[run_id]
        if not self._user_queues[user_id]:
            del self._user_queues[user_id]

        logger.info(
            f"SSE disconnected: user={user_id[:8]}... run={run_id[:8]}... "
            f"(remaining connections for run: {len(self._queues.get(run_id, set()))})"
        )

    async def broadcast_progress(
        self,
        run_id: str,
        progress: int,
        status: str,
        step_name: str | None = None,
        error: str | None = None,
        results: dict[str, Any] | None = None,
    ) -> None:
        """
        Broadcast a progress update to all clients watching a run.

        Args:
            run_id: UUID of the run
            progress: Progress percentage (0-100)
            status: Current run status
            step_name: Optional current step name
            error: Optional error message
            results: Optional results data
        """
        if status in TERMINAL_STATUSES:
            self._forget_replay(run_id)
        queues = self._queues.get(run_id, set())
        if not queues:
            return

        message = {
            "type": "progress_update",
            "run_id": run_id,
            "status": status,
            "progress": progress,
            "step_name": step_name,
            "error": error,
            "results": results,
            "timestamp": _get_timestamp(),
        }

        dead_queues: list[asyncio.Queue] = []
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(f"SSE queue full for run {run_id[:8]}..., dropping client")
                dead_queues.append(queue)

        for q in dead_queues:
            self._queues[run_id].discard(q)
            # Also remove from _user_queues to prevent leaked connection accounting
            for user_id, user_queue_set in list(self._user_queues.items()):
                user_queue_set.discard((run_id, q))
                if not user_queue_set:
                    del self._user_queues[user_id]

        if dead_queues:
            logger.info(f"Cleaned up {len(dead_queues)} full queues for run {run_id[:8]}...")

        # On terminal status, push None sentinel so generators stop
        if status in TERMINAL_STATUSES:
            self._forget_replay(run_id)
            for queue in list(self._queues.get(run_id, set())):
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)

    async def broadcast_event(self, run_id: str, event: dict[str, Any]) -> None:
        """
        Broadcast an activity event (e.g. a discovery-agent step) to clients watching a run.

        Events are kept per run so a client that connects mid-run can replay them (see
        ``recent_events``); past MAX_RECENT_EVENTS the oldest narration makes room.
        """
        message = {
            "type": "agent_event",
            "run_id": run_id,
            "event": event,
            "timestamp": _get_timestamp(),
        }
        recent = self._recent_events.setdefault(run_id, [])
        self._recent_events.move_to_end(run_id)
        recent.append(message)
        _trim_replay(recent)
        while len(self._recent_events) > MAX_REPLAY_RUNS:
            self._recent_events.popitem(last=False)
        self._send(run_id, message)

    async def broadcast_search_progress(self, run_id: str, search_id: str, progress: float) -> None:
        """
        Broadcast how far one cluster search has got. Progress is the search's current state,
        not a step of the run's history: only the latest value per search is kept for replay
        (see ``search_progress``).
        """
        latest = self._search_progress.setdefault(run_id, {})
        self._search_progress.move_to_end(run_id)
        latest[search_id] = progress
        while len(self._search_progress) > MAX_REPLAY_RUNS:
            self._search_progress.popitem(last=False)
        self._send(
            run_id,
            {
                "type": "search_progress",
                "run_id": run_id,
                "search_id": search_id,
                "progress": progress,
                "timestamp": _get_timestamp(),
            },
        )

    def _send(self, run_id: str, message: dict[str, Any]) -> None:
        for queue in list(self._queues.get(run_id, set())):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(message)

    def _forget_replay(self, run_id: str) -> None:
        self._recent_events.pop(run_id, None)
        self._search_progress.pop(run_id, None)

    def recent_events(self, run_id: str) -> list[dict[str, Any]]:
        """Recent activity events of a run (oldest first)."""
        return list(self._recent_events.get(run_id, ()))

    def search_progress(self, run_id: str) -> dict[str, float]:
        """Latest progress (%) of each cluster search of a run."""
        return dict(self._search_progress.get(run_id, {}))

    def get_connection_count(self, run_id: str) -> int:
        """Get the number of active connections for a run."""
        return len(self._queues.get(run_id, set()))

    def get_total_connections(self) -> int:
        """Get the total number of active connections across all runs."""
        return sum(len(qs) for qs in self._queues.values())


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# Module-level singleton accessor
_manager: SSEConnectionManager | None = None


def get_connection_manager() -> SSEConnectionManager:
    """Get the singleton SSEConnectionManager instance."""
    global _manager
    if _manager is None:
        _manager = SSEConnectionManager()
    return _manager
