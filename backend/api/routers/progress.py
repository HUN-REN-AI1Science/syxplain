"""
Progress webhook router.

Provides endpoints for Slurm workers to push progress updates
back to the backend.
"""

import asyncio
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.api.sse.connection_manager import get_connection_manager
from backend.core.config import get_compute_settings
from backend.core.constants import RunStatus
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["Internal"])

# Track cancel tasks (prevents GC of fire-and-forget asyncio tasks)
_cancel_tasks: set[asyncio.Task] = set()

# Legacy workers (no task_key) report 0-100% for a single PySR task; the endpoint
# scales that into this range of the overall progress bar. Keyed tasks (launched by
# the discovery agent) do not move the bar — the orchestrator drives it — and are
# streamed to the activity feed instead.
TASK_PROGRESS_RANGES = {
    "pysr": (25, 75),
}


class WorkerProgressUpdate(BaseModel):
    """Progress update from a Slurm worker."""

    progress: int = Field(..., ge=0, le=100, description="Progress percentage 0-100")
    status: str | None = Field(None, description="Human-readable status message")
    step_name: str | None = Field(None, description="Current step name")
    details: dict[str, Any] | None = Field(None, description="Additional details")
    task_type: str | None = Field(None, description="Task type (pysr)")
    task_key: str | None = Field(None, description="Task key within the run (e.g. pysr_2)")


class WorkerErrorReport(BaseModel):
    """Error report from a Slurm worker."""

    error: str = Field(..., description="Error message")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
    task_key: str | None = Field(None, description="Task key within the run (e.g. pysr_2)")


class WorkerCompletionReport(BaseModel):
    """Completion report from a Slurm worker."""

    results: dict[str, Any] = Field(..., description="Task results")
    task_key: str | None = Field(None, description="Task key within the run (e.g. pysr_2)")


def _store_task_result(run: Run, task_key: str, result: dict[str, Any]) -> bool:
    """
    Store one keyed task's result under Run.results["tasks"] (reassign so JSONB is dirty).
    A late callback for a finished run is ignored, so it cannot leak into the final results.
    """
    if RunStatus.is_terminal(run.status):
        logger.info(
            f"[Run {str(run.id)[:8]}] Ignoring late {task_key} callback; run is {run.status}"
        )
        return False
    results = dict(run.results or {})
    tasks = dict(results.get("tasks") or {})
    tasks[task_key] = result
    results["tasks"] = tasks
    run.results = results
    return True


def _validate_worker_token(token: str) -> bool:
    """
    Validate the worker callback token using constant-time comparison.

    Uses secrets.compare_digest to prevent timing attacks that could
    allow an attacker to guess the token byte-by-byte.
    """
    compute_settings = get_compute_settings()
    expected_token = compute_settings.worker_callback_token

    if not expected_token:
        # No token configured - reject all requests
        logger.warning("Worker callback token not configured - rejecting request")
        return False

    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(token, expected_token)


async def _cancel_slurm_jobs(run_id: str, slurm_job_ids: dict[str, Any]) -> None:
    """
    Cancel all Slurm jobs for a run to prevent orphaned cluster resources.
    """
    try:
        from backend.infrastructure.slurm import get_slurm_backend

        backend = get_slurm_backend()

        async def _cancel_one(job_type: str, job_id: str) -> None:
            try:
                await backend.cancel_task(job_id)
                logger.info(f"[Run {run_id[:8]}] Cancelled {job_type}: {job_id}")
            except Exception as e:
                logger.warning(f"[Run {run_id[:8]}] Failed to cancel {job_type} {job_id}: {e}")

        await asyncio.gather(*(_cancel_one(jt, jid) for jt, jid in slurm_job_ids.items() if jid))
    except Exception as e:
        logger.error(f"[Run {run_id[:8]}] Error cancelling Slurm jobs: {e}")


@router.post("/progress/{run_id}")
async def receive_progress(
    run_id: str,
    progress: WorkerProgressUpdate,
    x_worker_token: str = Header(..., alias="X-Worker-Token"),
):
    """
    Receive progress update from a Slurm worker.

    This endpoint is called by workers running on the Slurm cluster
    to report their progress back to the backend.

    Args:
        run_id: UUID of the run being processed
        progress: Progress update data
        x_worker_token: Authentication token from worker

    Returns:
        Acknowledgment message
    """
    # Validate token
    if not _validate_worker_token(x_worker_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )

    try:
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()

            if not run:
                logger.warning(f"Progress update for unknown run: {run_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run {run_id} not found",
                )

            if progress.task_key:
                # Keyed (agent-launched) task: stream to the activity feed only
                manager = get_connection_manager()
                await manager.broadcast_event(
                    run_id=run_id,
                    event={
                        "kind": "search_progress",
                        "text": f"{progress.task_key}: {progress.status or progress.step_name} "
                        f"({progress.progress}%)",
                        "search_id": progress.task_key,
                        "progress": progress.progress,
                    },
                )
                return {"status": "ok", "progress": run.progress}

            # Scale worker progress into allocated range
            actual_progress = progress.progress
            if progress.task_type and progress.task_type in TASK_PROGRESS_RANGES:
                start, end = TASK_PROGRESS_RANGES[progress.task_type]
                actual_progress = round(start + (progress.progress / 100) * (end - start))

            # Only update if progress increases
            if actual_progress > (run.progress or 0):
                run.progress = actual_progress
                db.commit()
                logger.info(
                    f"[Run {run_id[:8]}] Progress: {actual_progress}%"
                    + (
                        f" (raw {progress.progress}% from {progress.task_type})"
                        if progress.task_type
                        else ""
                    )
                    + (f" - {progress.status}" if progress.status else "")
                )

                # Broadcast progress update via SSE
                manager = get_connection_manager()
                await manager.broadcast_progress(
                    run_id=run_id,
                    progress=actual_progress,
                    status=run.status,
                    step_name=progress.step_name,
                )

        return {"status": "ok", "progress": actual_progress}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating progress for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update progress",
        )


@router.post("/error/{run_id}")
async def receive_error(
    run_id: str,
    error: WorkerErrorReport,
    x_worker_token: str = Header(..., alias="X-Worker-Token"),
):
    """
    Receive error report from a Slurm worker.

    Called when a worker encounters a fatal error during execution.

    Args:
        run_id: UUID of the run being processed
        error: Error report data
        x_worker_token: Authentication token from worker

    Returns:
        Acknowledgment message
    """
    # Validate token
    if not _validate_worker_token(x_worker_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )

    logger.error(f"Worker error for run {run_id}: {error.error}")

    try:
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()

            if not run:
                logger.warning(f"Error report for unknown run: {run_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run {run_id} not found",
                )

            if error.task_key:
                # One agent-launched search failed: record it, the run continues.
                # The orchestrator decides whether the run as a whole has failed.
                _store_task_result(run, error.task_key, {"status": "error", "error": error.error})
                db.commit()
                manager = get_connection_manager()
                await manager.broadcast_event(
                    run_id=run_id,
                    event={
                        "kind": "search_failed",
                        "text": f"{error.task_key} failed on the cluster: {error.error[:200]}",
                        "search_id": error.task_key,
                    },
                )
                return {"status": "ok", "run_status": run.status}

            run.status = RunStatus.FAILED
            run.error = error.error
            slurm_job_ids = run.slurm_job_ids
            db.commit()
            logger.info(f"[Run {run_id[:8]}] Marked as failed: {error.error}")

            # Cancel other Slurm jobs to avoid orphaned compute resources
            if slurm_job_ids:
                task = asyncio.create_task(_cancel_slurm_jobs(run_id, slurm_job_ids))
                _cancel_tasks.add(task)
                task.add_done_callback(_cancel_tasks.discard)

            # Broadcast error via SSE
            manager = get_connection_manager()
            await manager.broadcast_progress(
                run_id=run_id,
                progress=run.progress or 0,
                status=RunStatus.FAILED,
                error=error.error,
            )

        return {"status": "ok", "run_status": "failed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording failure for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record error",
        )


@router.post("/complete/{run_id}")
async def receive_completion(
    run_id: str,
    completion: WorkerCompletionReport,
    x_worker_token: str = Header(..., alias="X-Worker-Token"),
):
    """
    Receive completion report from a Slurm worker.

    Called when a worker successfully completes a compute task.
    Note: This only marks the compute portion as complete - the
    orchestrator will continue with LLM operations.

    Args:
        run_id: UUID of the run being processed
        completion: Completion report with results
        x_worker_token: Authentication token from worker

    Returns:
        Acknowledgment message
    """
    # Validate token
    if not _validate_worker_token(x_worker_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )

    logger.info(f"Worker completion for run {run_id}")

    try:
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()

            if not run:
                logger.warning(f"Completion report for unknown run: {run_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run {run_id} not found",
                )

            if completion.task_key:
                _store_task_result(run, completion.task_key, completion.results)
                db.commit()
                logger.info(f"[Run {run_id[:8]}] Stored results for {completion.task_key}")
                return {"status": "ok", "results_stored": True}

            # Store intermediate results - don't mark as completed yet
            # The orchestrator will continue with LLM processing
            if run.results:
                # Merge with existing results
                run.results = {**run.results, **completion.results}
            else:
                run.results = completion.results

            # Don't override progress — worker progress is already scaled
            # into the correct range by receive_progress()
            db.commit()
            logger.info(f"[Run {run_id[:8]}] Compute results stored, progress at {run.progress}%")

            # Broadcast completion via SSE
            manager = get_connection_manager()
            await manager.broadcast_progress(
                run_id=run_id,
                progress=run.progress or 0,
                status=run.status,
                results=run.results,
            )

        return {"status": "ok", "results_stored": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing results for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store results",
        )


@router.get("/input/{run_id}")
async def get_job_input(
    run_id: str,
    task_type: str,
    task_key: str | None = None,
    worker_version: str | None = None,
    x_worker_token: str = Header(..., alias="X-Worker-Token"),
):
    """
    Get input data for a compute task.

    Called by Slurm workers to fetch their input data.

    Args:
        run_id: UUID of the run being processed
        task_type: Type of task (e.g., "pysr")
        task_key: Key of the task within the run (e.g., "pysr_2"); defaults to task_type
        x_worker_token: Authentication token from worker

    Returns:
        Input data for the task
    """
    if not _validate_worker_token(x_worker_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker token",
        )

    try:
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()

            if not run:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run {run_id} not found",
                )

            key = task_key or task_type
            if not run.input_data or key not in run.input_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Input for task {key} not found",
                )

            input_data = run.input_data[key]
            if not input_data or (isinstance(input_data, dict) and input_data.get("fetched")):
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail=f"Input for task {key} was already fetched",
                )

            # Clear input after fetch (one-time use, saves DB space); keep the worker version
            updated_input = dict(run.input_data)
            updated_input[key] = {"fetched": True, "worker_version": worker_version or "<3.0"}
            run.input_data = updated_input
            db.commit()

            logger.info(f"Input fetched for run {run_id}, task {key} (worker {worker_version})")
            return {"input": input_data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching input for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch input",
        )


@router.get("/health")
async def worker_health():
    """
    Health check endpoint for workers.

    Workers can call this to verify connectivity to the backend
    before starting their tasks.

    Returns:
        Health status
    """
    return {"status": "healthy", "service": "syxplain-backend"}
