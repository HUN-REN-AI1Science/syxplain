"""
WebSocket endpoint for real-time progress updates.

Provides a WebSocket connection at /ws/progress/{run_id} that streams
progress updates to authenticated clients.
"""

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.api.websocket.connection_manager import get_connection_manager
from backend.core.config import get_auth_settings
from backend.core.exceptions import AuthenticationError, ValidationError
from backend.core.security import decode_jwt_token
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/progress/{run_id}")
async def websocket_progress(
    websocket: WebSocket,
    run_id: str,
    token: str = Query(..., description="JWT authentication token"),
):
    """
    WebSocket endpoint for real-time progress updates.

    Authenticates the connection using a JWT token passed as a query parameter,
    verifies the user owns the run, then streams progress updates until the
    run completes or the connection is closed.

    Args:
        websocket: The WebSocket connection
        run_id: UUID of the run to watch
        token: JWT authentication token (query param)
    """
    manager = get_connection_manager()
    user_id: str | None = None

    try:
        # Authenticate via JWT
        settings = get_auth_settings()
        try:
            payload = decode_jwt_token(token, settings)
            user_id = payload.get("sub")
            if not user_id:
                logger.warning("WebSocket auth failed: missing user ID in token")
                await websocket.close(code=4001, reason="Invalid token")
                return
        except AuthenticationError as e:
            logger.warning(f"WebSocket auth failed: {e.message}")
            await websocket.close(code=4001, reason=e.message)
            return

        # Verify user owns the run
        try:
            parsed_run_id = parse_uuid(run_id, "run_id")
        except ValidationError:
            logger.warning(f"WebSocket: invalid run_id format: {run_id}")
            await websocket.close(code=4004, reason="Invalid run ID")
            return

        def _fetch_run_from_db(run_uuid, uid):
            """Fetch run data in a thread to avoid blocking the event loop."""
            with get_db_session() as db:
                run = db.query(Run).filter(Run.id == run_uuid).first()
                if not run:
                    return None, "not_found", None
                if str(run.user_id) != str(uid):
                    return None, "access_denied", None
                return (
                    run.id,
                    "ok",
                    {
                        "status": run.status,
                        "progress": run.progress or 0,
                        "error": run.error,
                        "results": run.results,
                    },
                )

        _, check_result, run_data = await asyncio.to_thread(
            _fetch_run_from_db, parsed_run_id, user_id
        )

        if check_result == "not_found":
            logger.warning(f"WebSocket: run {run_id} not found")
            await websocket.close(code=4004, reason="Run not found")
            return

        if check_result == "access_denied":
            logger.warning(f"WebSocket: user {user_id[:8]}... doesn't own run {run_id[:8]}...")
            await websocket.close(code=4003, reason="Access denied")
            return

        # Get initial state
        initial_status = run_data["status"]
        initial_progress = run_data["progress"]
        initial_error = run_data["error"]
        initial_results = run_data["results"]

        # Accept connection and register
        await manager.connect(websocket, run_id, user_id)

        # Send initial state
        await manager.send_initial_state(
            websocket,
            run_id,
            initial_status,
            initial_progress,
            initial_error,
            initial_results,
        )

        # Keep connection alive and handle messages
        while True:
            try:
                data = await websocket.receive_json()

                # Handle ping/pong for keepalive
                if data.get("type") == "ping":
                    await manager.send_pong(websocket)

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected normally: run={run_id[:8]}...")
                break
            except Exception as e:
                logger.warning(f"WebSocket error receiving message: {e}")
                break

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if user_id:
            manager.disconnect(websocket, run_id, user_id)
