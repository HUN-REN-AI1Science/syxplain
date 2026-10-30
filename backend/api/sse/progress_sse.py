"""
SSE endpoint for real-time progress updates.

Provides a GET endpoint at /api/sse/progress/{run_id} that streams
progress updates to authenticated clients using Server-Sent Events.

Accepts JWT via either Authorization header or ?token= query parameter.
The query parameter is needed because the browser's native EventSource API
does not support custom headers.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sse_starlette.sse import EventSourceResponse

from backend.api.sse.connection_manager import get_connection_manager
from backend.core.config import get_auth_settings
from backend.core.exceptions import ValidationError
from backend.core.security import User, _authenticate_jwt, security
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run
from backend.services.progress_service import get_progress_phases
from backend.utils import parse_uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sse", tags=["SSE"])

TERMINAL_STATUSES = ("completed", "failed", "timeout", "cancelled")


async def _get_sse_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = Query(None, description="JWT token (alternative to Authorization header)"),
) -> User:
    """Authenticate via Authorization header or ?token= query parameter."""
    settings = get_auth_settings()

    # Prefer Authorization header, fall back to query param
    if credentials:
        return _authenticate_jwt(credentials, settings)

    if token:
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        return _authenticate_jwt(creds, settings)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (Bearer header or ?token= query parameter)",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/progress/{run_id}")
async def sse_progress(
    run_id: str,
    user: User = Depends(_get_sse_user),
):
    """
    SSE endpoint for real-time progress updates.

    Authenticates via standard Bearer JWT header, verifies the user owns
    the run, then streams progress events until the run completes or the
    client disconnects.

    Args:
        run_id: UUID of the run to watch
        user: Authenticated user (injected via Depends)
    """
    # Validate run_id format
    try:
        parsed_run_id = parse_uuid(run_id, "run_id")
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid run ID format",
        )

    # Verify user owns the run and get initial state
    def _fetch_run_from_db(run_uuid, uid):
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
        _fetch_run_from_db, parsed_run_id, user.user_id
    )

    if check_result == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )

    if check_result == "access_denied":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    manager = get_connection_manager()

    async def event_generator():
        # Connect inside the generator so disconnect always runs in finally
        try:
            queue = manager.connect(run_id, user.user_id)
        except ConnectionError as e:
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": str(e)}),
            }
            return

        try:
            # Yield initial state as first event
            initial_event = {
                "type": "initial_state",
                "run_id": run_id,
                "status": run_data["status"],
                "progress": run_data["progress"],
                "error": run_data["error"],
                # Per-task intermediate results are internal to the orchestrator
                "results": {k: v for k, v in (run_data["results"] or {}).items() if k != "tasks"}
                or None,
                "recent_events": manager.recent_events(run_id),
                "search_progress": manager.search_progress(run_id),
                # A client that rejoins (page reload, history) has no run response to take
                # the phases from
                "progress_phases": get_progress_phases(),
            }
            yield {
                "event": "initial_state",
                "data": json.dumps(initial_event),
            }

            # If already terminal, stop immediately
            if run_data["status"] in TERMINAL_STATUSES:
                return

            # Stream updates from queue
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield {"comment": "keepalive"}
                    continue

                # None sentinel means stream is done
                if message is None:
                    return

                yield {"event": message["type"], "data": json.dumps(message)}

                # Stop after terminal status
                if message.get("status") in TERMINAL_STATUSES:
                    return

        finally:
            manager.disconnect(queue, run_id, user.user_id)

    return EventSourceResponse(
        event_generator(),
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
