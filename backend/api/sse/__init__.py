"""SSE API package for real-time progress updates."""

from backend.api.sse.connection_manager import SSEConnectionManager, get_connection_manager

__all__ = ["SSEConnectionManager", "get_connection_manager"]
