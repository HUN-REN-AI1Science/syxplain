"""
WebSocket endpoint for real-time PySR equation streaming.

Provides live updates of equation discovery during PySR training.
"""
import asyncio
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """
    Manages WebSocket connections for run-specific streaming.

    Thread-safe connection registry that allows broadcasting
    messages to all clients watching a specific run.
    """

    def __init__(self):
        # run_id -> set of WebSocket connections
        self.connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, run_id: str, websocket: WebSocket):
        """Accept and register a WebSocket connection for a run."""
        await websocket.accept()
        async with self._lock:
            if run_id not in self.connections:
                self.connections[run_id] = set()
            self.connections[run_id].add(websocket)
        logger.info(f"WebSocket connected for run {run_id[:8]}...")

    async def disconnect(self, run_id: str, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            if run_id in self.connections:
                self.connections[run_id].discard(websocket)
                if not self.connections[run_id]:
                    del self.connections[run_id]
        logger.debug(f"WebSocket disconnected for run {run_id[:8]}...")

    async def broadcast(self, run_id: str, message: str):
        """Broadcast a message to all clients watching a run."""
        async with self._lock:
            if run_id not in self.connections:
                return
            websockets = list(self.connections[run_id])

        # Send to all connected clients
        disconnected = []
        for websocket in websockets:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.append(websocket)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                if run_id in self.connections:
                    for ws in disconnected:
                        self.connections[run_id].discard(ws)

    def has_connections(self, run_id: str) -> bool:
        """Check if a run has any active WebSocket connections."""
        return run_id in self.connections and len(self.connections[run_id]) > 0


# Global connection manager instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager


@router.websocket("/runs/{run_id}/live")
async def pysr_live_stream(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for streaming live PySR equation updates.

    Clients connect during PySR training to receive real-time
    Hall of Fame equation updates.
    """
    from backend.services.pysr_streaming import read_stream
    import json

    await manager.connect(run_id, websocket)
    logger.info(f"WS Handling loop started for {run_id}")
    last_content = ""

    try:
        while True:
            # Poll the stream file for updates
            content = read_stream(run_id)

            if content:
                # logger.debug(f"Read content for {run_id}: {len(content)} chars")
                pass

            if content and content != last_content:
                last_content = content
                message = json.dumps({
                    "type": "equations",
                    "content": content
                })
                try:
                    await websocket.send_text(message)
                    logger.debug(f"Sent update to WS for {run_id}")
                except Exception as e:
                    logger.error(f"Failed to send WS message: {e}")
                    break

            # Check for client disconnect or sleep
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(run_id, websocket)
