"""WebSocket API package for real-time progress updates."""

from backend.api.websocket.connection_manager import ConnectionManager, get_connection_manager

__all__ = ["ConnectionManager", "get_connection_manager"]
