"""
Progress webhook router.

Provides endpoints for Slurm workers to push progress updates
back to the backend.
"""
import logging
import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.config import get_compute_settings
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["Internal"])


class WorkerProgressUpdate(BaseModel):
    """Progress update from a Slurm worker."""
    progress: int = Field(..., ge=0, le=100, description="Progress percentage 0-100")
    status: Optional[str] = Field(None, description="Human-readable status message")
    step_name: Optional[str] = Field(None, description="Current step name")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class WorkerErrorReport(BaseModel):
    """Error report from a Slurm worker."""
    error: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


class WorkerCompletionReport(BaseModel):
    """Completion report from a Slurm worker."""
    results: Dict[str, Any] = Field(..., description="Task results")


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

    logger.debug(
        f"Progress update for run {run_id}: {progress.progress}% - {progress.status}"
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

            # Only update if progress increases
            if progress.progress > (run.progress or 0):
                run.progress = progress.progress
                db.commit()
                logger.info(
                    f"[Run {run_id[:8]}] Progress: {progress.progress}%"
                    + (f" - {progress.status}" if progress.status else "")
                )

        return {"status": "ok", "progress": progress.progress}

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

            run.status = "failed"
            run.error = error.error
            db.commit()
            logger.info(f"[Run {run_id[:8]}] Marked as failed: {error.error}")

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

            # Store intermediate results - don't mark as completed yet
            # The orchestrator will continue with LLM processing
            if run.results:
                # Merge with existing results
                run.results = {**run.results, **completion.results}
            else:
                run.results = completion.results

            # Set progress to indicate compute portion complete
            run.progress = 70  # Typical progress after compute phase
            db.commit()
            logger.info(f"[Run {run_id[:8]}] Compute results stored")

        return {"status": "ok", "results_stored": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error storing results for {run_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store results",
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
