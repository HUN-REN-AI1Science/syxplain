"""
WebSocket connection manager for real-time progress updates.

Manages WebSocket connections per run_id and broadcasts progress updates
to all connected clients watching a specific run.
"""

import asyncio
import contextlib
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Singleton manager for WebSocket connections.

    Tracks active connections per run_id and provides methods to
    broadcast progress updates to all clients watching a run.
    """

    _instance: "ConnectionManager | None" = None
    _lock: asyncio.Lock | None = None

    def __new__(cls) -> "ConnectionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connections = defaultdict(set)
            cls._instance._user_connections = defaultdict(set)
        return cls._instance

    @property
    def _connections(self) -> dict[str, set[WebSocket]]:
        """Connections indexed by run_id."""
        return self.__dict__.get("_connections_store", defaultdict(set))

    @_connections.setter
    def _connections(self, value: dict[str, set[WebSocket]]) -> None:
        self.__dict__["_connections_store"] = value

    @property
    def _user_connections(self) -> dict[str, set[tuple[str, WebSocket]]]:
        """Connections indexed by user_id, storing (run_id, websocket) tuples."""
        return self.__dict__.get("_user_connections_store", defaultdict(set))

    @_user_connections.setter
    def _user_connections(self, value: dict[str, set[tuple[str, WebSocket]]]) -> None:
        self.__dict__["_user_connections_store"] = value

    async def connect(self, websocket: WebSocket, run_id: str, user_id: str) -> None:
        """
        Register a new WebSocket connection for a run.

        Args:
            websocket: The WebSocket connection
            run_id: UUID of the run being watched
            user_id: UUID of the authenticated user
        """
        await websocket.accept()
        self._connections[run_id].add(websocket)
        self._user_connections[user_id].add((run_id, websocket))
        logger.info(
            f"WebSocket connected: user={user_id[:8]}... run={run_id[:8]}... "
            f"(total connections for run: {len(self._connections[run_id])})"
        )

    def disconnect(self, websocket: WebSocket, run_id: str, user_id: str) -> None:
        """
        Remove a WebSocket connection.

        Args:
            websocket: The WebSocket connection to remove
            run_id: UUID of the run being watched
            user_id: UUID of the authenticated user
        """
        self._connections[run_id].discard(websocket)
        self._user_connections[user_id].discard((run_id, websocket))

        # Clean up empty sets
        if not self._connections[run_id]:
            del self._connections[run_id]
        if not self._user_connections[user_id]:
            del self._user_connections[user_id]

        logger.info(
            f"WebSocket disconnected: user={user_id[:8]}... run={run_id[:8]}... "
            f"(remaining connections for run: {len(self._connections.get(run_id, set()))})"
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
        connections = self._connections.get(run_id, set())
        if not connections:
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

        # Send to all connected clients, removing dead connections
        dead_connections: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        for ws in dead_connections:
            self._connections[run_id].discard(ws)

        if dead_connections:
            logger.info(f"Cleaned up {len(dead_connections)} dead connections for run {run_id[:8]}...")

        # Close connections after terminal status — the run is done,
        # no more updates will be sent. The server-side close causes
        # the handler's receive_json() to raise WebSocketDisconnect.
        TERMINAL_STATUSES = ("completed", "failed", "timeout", "cancelled")
        if status in TERMINAL_STATUSES:
            live_connections = [ws for ws in connections if ws not in dead_connections]
            for websocket in live_connections:
                with contextlib.suppress(Exception):
                    await websocket.close(code=1000, reason=f"Run {status}")

    async def send_initial_state(
        self,
        websocket: WebSocket,
        run_id: str,
        status: str,
        progress: int,
        error: str | None = None,
        results: dict[str, Any] | None = None,
    ) -> None:
        """
        Send the initial state to a newly connected client.

        Args:
            websocket: The WebSocket connection
            run_id: UUID of the run
            status: Current run status
            progress: Current progress percentage
            error: Optional error message
            results: Optional results data
        """
        message = {
            "type": "initial_state",
            "run_id": run_id,
            "status": status,
            "progress": progress,
            "error": error,
            "results": results,
        }
        await websocket.send_json(message)

    async def send_pong(self, websocket: WebSocket) -> None:
        """Send a pong response to a ping request."""
        await websocket.send_json({"type": "pong"})

    def get_connection_count(self, run_id: str) -> int:
        """Get the number of active connections for a run."""
        return len(self._connections.get(run_id, set()))

    def get_total_connections(self) -> int:
        """Get the total number of active connections across all runs."""
        return sum(len(conns) for conns in self._connections.values())


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# Module-level singleton accessor
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Get the singleton ConnectionManager instance."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
