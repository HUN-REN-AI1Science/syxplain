"""
Analysis service for background processing.

Manages the lifecycle of analysis runs using asyncio background tasks.
SHAP and PySR compute tasks run on Slurm, not locally.
"""

import asyncio
import logging
from typing import Any

from backend.core.constants import RunStatus
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import File as DbFile
from backend.infrastructure.database.models import Run
from backend.services.file_service import get_file_service
from backend.services.orchestrator_service import AnalysisCancelledError

logger = logging.getLogger(__name__)

# Track running analysis tasks (prevents GC of asyncio tasks)
_running_tasks: dict[str, asyncio.Task] = {}

# Track broadcast tasks (prevents GC of fire-and-forget SSE broadcasts)
_broadcast_tasks: set[asyncio.Task] = set()


def update_run_status(
    run_id: str,
    status: str,
    results: dict[str, Any] | None = None,
    error: str | None = None,
    progress: int | None = None,
) -> None:
    """
    Update run status in the database and broadcast via SSE.

    Args:
        run_id: The run UUID as string
        status: New status value
        results: Optional results dictionary
        error: Optional error message
        progress: Optional progress percentage
    """
    from datetime import datetime

    final_progress = progress

    try:
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = status
                # Set start_time when transitioning to running
                if status == RunStatus.RUNNING and run.start_time is None:
                    run.start_time = datetime.utcnow()
                # Set finish_time for terminal states
                if RunStatus.is_terminal(status):
                    run.finish_time = datetime.utcnow()
                if results:
                    run.results = results
                if error:
                    run.error = error
                # Set progress based on status or explicit value
                if progress is not None:
                    run.progress = progress
                    final_progress = progress
                elif status == RunStatus.COMPLETED:
                    run.progress = 100
                    final_progress = 100
                elif status in (RunStatus.FAILED, RunStatus.TIMEOUT, RunStatus.CANCELLED):
                    # Keep current progress for failed/timeout/cancelled
                    final_progress = run.progress or 0
                db.commit()
    except Exception as e:
        logger.error(f"Failed to update run status for {run_id}: {e}")
        return

    # Broadcast via SSE
    _broadcast_status_update(run_id, status, final_progress or 0, error, results)


def _broadcast_status_update(
    run_id: str,
    status: str,
    progress: int,
    error: str | None = None,
    results: dict[str, Any] | None = None,
) -> None:
    """Broadcast status update via SSE."""
    try:
        from backend.api.sse.connection_manager import get_connection_manager

        manager = get_connection_manager()

        # Try to get running event loop
        try:
            asyncio.get_running_loop()
            task = asyncio.ensure_future(
                manager.broadcast_progress(
                    run_id=run_id,
                    progress=progress,
                    status=status,
                    error=error,
                    results=results,
                )
            )
            _broadcast_tasks.add(task)
            task.add_done_callback(_broadcast_tasks.discard)
        except RuntimeError:
            # No running event loop - skip broadcast
            pass
    except Exception as e:
        logger.debug(f"Could not broadcast status update: {e}")


async def _run_analysis(
    run_id: str,
    problem_desc: dict[str, Any],
    csv_filename: str,
    analysis_type: str = "quick",
    deep_research_model: str | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
    user_openai_key: str | None = None,
) -> None:
    """
    Async function that runs the orchestrated analysis.

    Performs the actual analysis work by delegating to the orchestrator,
    which coordinates compute tasks (SHAP, PySR) on Slurm and LLM operations.
    """
    # Yield control so the HTTP response (with run_id) is sent first
    await asyncio.sleep(0)

    from backend.core.logging import configure_debug_mode, configure_logging

    configure_logging()
    configure_debug_mode()

    # Initialize Langfuse tracing
    from backend.infrastructure.monitoring import init_langfuse

    init_langfuse()

    logger.info(f"Analysis task started for Run ID: {run_id}")

    try:
        # Load data from DB
        file_service = get_file_service()

        with get_db_session() as db:
            db_file = (
                db.query(DbFile)
                .filter(DbFile.filename == csv_filename)
                .order_by(DbFile.created_at.desc())
                .first()
            )

            if not db_file:
                raise Exception(f"File {csv_filename} not found in database")

            logger.info(f"Loading data for {csv_filename} from DB")
            data = file_service.parse_dataframe(db_file.content, csv_filename)

        # Get user_id from run record
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()
            user_id = str(run.user_id)

        # Run orchestrated analysis
        from backend.services.orchestrator_service import run_orchestrated_analysis

        await run_orchestrated_analysis(
            run_id=run_id,
            problem_desc=problem_desc,
            data=data,
            user_id=user_id,
            analysis_type=analysis_type,
            deep_research_model=deep_research_model,
            user_api_key=user_api_key,
            user_model=user_model,
            user_openai_key=user_openai_key,
        )

        logger.info(f"Run {run_id} completed successfully")

    except asyncio.CancelledError:
        logger.info(f"Run {run_id} was cancelled")
        update_run_status(run_id, RunStatus.CANCELLED, error="Analysis cancelled by user")
        raise
    except AnalysisCancelledError:
        logger.info(f"Run {run_id} was cancelled by user")
        # Don't overwrite — cancel_run already set status to "cancelled"
    except Exception as e:
        error_msg = str(e)
        update_run_status(run_id, RunStatus.FAILED, error=error_msg)
        logger.error(f"Run {run_id} failed: {e}", exc_info=True)


def start_analysis_run(
    problem_desc: dict[str, Any],
    csv_filename: str,
    user_id: str,
    analysis_type: str = "quick",
    deep_research_model: str | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
    user_openai_key: str | None = None,
) -> str:
    """
    Create a run record and start background processing.

    Args:
        problem_desc: Problem description dictionary
        csv_filename: Name of the file to analyze
        user_id: Owner's UUID as string
        analysis_type: 'quick' or 'deep'
        deep_research_model: Model for deep analysis
        user_api_key: Optional user-provided Gemini API key (not stored, only in memory)
        user_model: Optional user-specified Gemini model
        user_openai_key: Optional user-provided OpenAI API key for deep research

    Returns:
        The run UUID as string
    """
    # Create Run record in DB (user_api_key is NOT stored)
    with get_db_session() as db:
        run = Run(
            problem_description=problem_desc,
            csv_filename=csv_filename,
            status=RunStatus.PENDING,
            user_id=user_id,
            analysis_type=analysis_type,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = str(run.id)

    logger.info(
        f"Starting background task for Run ID: {run_id} "
        f"(analysis_type={analysis_type}, model={deep_research_model}, using_user_key={user_api_key is not None})"
    )

    # Start async background task (user keys passed in memory only)
    task = asyncio.create_task(
        _run_analysis(
            run_id,
            problem_desc,
            csv_filename,
            analysis_type,
            deep_research_model,
            user_api_key=user_api_key,
            user_model=user_model,
            user_openai_key=user_openai_key,
        )
    )
    _running_tasks[run_id] = task

    # Cleanup when done
    def cleanup_task(t: asyncio.Task) -> None:
        _running_tasks.pop(run_id, None)

    task.add_done_callback(cleanup_task)

    return run_id
