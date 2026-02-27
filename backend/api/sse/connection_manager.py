"""
SSE connection manager for real-time progress updates.

Manages asyncio.Queue instances per SSE client and broadcasts progress updates
to all connected clients watching a specific run.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "failed", "timeout", "cancelled")


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
        """
        queue: asyncio.Queue = asyncio.Queue()
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

        if dead_queues:
            logger.info(
                f"Cleaned up {len(dead_queues)} full queues for run {run_id[:8]}..."
            )

        # On terminal status, push None sentinel so generators stop
        if status in TERMINAL_STATUSES:
            for queue in list(self._queues.get(run_id, set())):
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

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
