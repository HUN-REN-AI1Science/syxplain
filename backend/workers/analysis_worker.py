"""
Analysis worker for background processing.

Manages the lifecycle of analysis runs including process spawning,
status updates, and timeout handling.
"""

import json
import logging
import multiprocessing

from datetime import datetime, timedelta
from typing import Any, Dict, Optional


import pandas as pd

from backend.core.config import get_settings
from backend.infrastructure.database.connection import get_db_session, dispose_engine
from backend.infrastructure.database.models import Run, File as DbFile
from backend.services.file_service import FileService

logger = logging.getLogger(__name__)

# Global registry for active processes
active_processes: Dict[str, multiprocessing.Process] = {}


def cleanup_processes() -> None:
    """
    Check active processes and clean up finished ones.

    Should be called periodically to release resources
    from completed processes.
    """
    finished_run_ids = []
    for run_id, process in active_processes.items():
        if not process.is_alive():
            process.join()  # Ensure resources are released
            finished_run_ids.append(run_id)
            logger.info(f"Process for run {run_id} has finished and was joined.")

    for run_id in finished_run_ids:
        del active_processes[run_id]
        # Clean up streaming registry
        try:
            from backend.services.pysr_streaming import unregister_stream
            unregister_stream(run_id)
        except Exception:
            pass


def update_run_status(
    run_id: str,
    status: str,
    results: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    progress: Optional[int] = None
) -> None:
    """
    Update run status in the database.

    Args:
        run_id: The run UUID as string
        status: New status value
        results: Optional results dictionary
        error: Optional error message
        progress: Optional progress percentage
    """
    try:
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = status
                if results:
                    run.results = results
                if error:
                    run.error = error
                # Set progress based on status or explicit value
                if progress is not None:
                    run.progress = progress
                elif status == "completed":
                    run.progress = 100
                elif status in ("failed", "timeout"):
                    # Keep current progress for failed/timeout
                    pass
                db.commit()
    except Exception as e:
        logger.error(f"Failed to update run status for {run_id}: {e}")


# Global manager for shared IPC objects
_manager = None

def get_manager():
    """Get or create global multiprocessing manager."""
    global _manager
    if _manager is None:
        _manager = multiprocessing.Manager()
    return _manager

def _run_worker(
    run_id: str,
    problem_desc: Dict[str, Any],
    csv_filename: str,
    analysis_type: str = "quick",
    deep_research_model: Optional[str] = None,
    stream_dict: Optional[Dict[str, Any]] = None
) -> None:
    """
    Worker function that runs in a separate process.

    Performs the actual analysis work including data loading,
    graph execution, and result storage.

    Args:
        run_id: The run UUID as string
        problem_desc: Problem description dictionary
        csv_filename: Name of the file to analyze
        analysis_type: 'quick' or 'deep'
        deep_research_model: Model for deep analysis
        stream_dict: Shared dictionary for live streaming (optional)
    """
    # Configure logging for this process
    from backend.core.logging import configure_logging, configure_debug_mode
    configure_logging()
    configure_debug_mode()

    # Initialize Langfuse tracing
    from backend.infrastructure.monitoring import init_langfuse
    init_langfuse()

    # Import syxplain_lib here to ensure Julia is initialized ONLY in this worker process
    from syxplain_lib import State, run_syxplain

    # Dispose of the engine to ensure fresh connections in this process
    dispose_engine()

    logger.info(f"Worker process started for Run ID: {run_id}")

    try:
        update_run_status(run_id, "running")

        # Load data from DB
        file_service = FileService()

        with get_db_session() as db:
            db_file = db.query(DbFile).filter(
                DbFile.filename == csv_filename
            ).order_by(DbFile.created_at.desc()).first()

            if not db_file:
                raise Exception(f"File {csv_filename} not found in database")

            logger.info(f"Loading data for {csv_filename} from DB")
            sample_data = file_service.parse_dataframe(db_file.content, csv_filename)

        # Prepare state
        problem_description_src = json.dumps(problem_desc, indent=2)

        # Initialize progress tracker with run_id
        from backend.services.progress_service import ProgressTracker
        progress = ProgressTracker(run_id=run_id)

        def entry_point(state: State) -> State:
            logger.info("Executing entry_point node")
            state["logger"] = progress
            progress.update_progress("initialization", status="Initializing analysis", details={
                "rows": len(sample_data),
                "columns": len(sample_data.columns)
            })

            state["data"] = sample_data
            state["problem_description_src"] = problem_description_src
            state["target_column"] = problem_desc["target_variable"]

            # Pass shared stream dict for live streaming
            if stream_dict is not None:
                state["stream_dict"] = stream_dict

            # Filter predictor columns to only include numeric columns
            all_predictors = list(problem_desc["features"].keys())
            numeric_predictors = []
            for col in all_predictors:
                if col not in sample_data.columns:
                    logger.warning(f"Excluding column from predictors (not found in data): {col}")
                elif not pd.api.types.is_numeric_dtype(sample_data[col]):
                    logger.warning(f"Excluding non-numeric column from predictors: {col}")
                else:
                    numeric_predictors.append(col)

            state["predictor_columns"] = numeric_predictors
            return state

        # Build and run the graph
        from syxplain_lib import (
            data_summary,
            llm_pysr_config_generator,
            pysr_with_generated_config,
            explain_pysr_equations,
            deep_research_node
        )
        from langgraph.graph import StateGraph, START, END

        logger.info(f"Building StateGraph (analysis_type={analysis_type})")
        g = StateGraph(State)
        g.add_node("entry_point", entry_point)
        g.add_node("data_summary", data_summary)
        g.add_node("pysr_config_generator", llm_pysr_config_generator)
        g.add_node("pysr_executor", pysr_with_generated_config)
        g.add_node("pysr_explainer", explain_pysr_equations)

        g.add_edge(START, "entry_point")
        g.add_edge("entry_point", "data_summary")
        g.add_edge("data_summary", "pysr_config_generator")
        g.add_edge("pysr_config_generator", "pysr_executor")

        # Conditionally add deep research step for deep analysis
        if analysis_type == "deep":
            g.add_node("deep_research", deep_research_node)
            g.add_edge("pysr_executor", "deep_research")
            g.add_edge("deep_research", "pysr_explainer")
        else:
            g.add_edge("pysr_executor", "pysr_explainer")

        g.add_edge("pysr_explainer", END)

        app = g.compile()
        logger.info("Invoking graph execution...")

        # Initialize state with our logger and analysis type
        initial_state = State()
        initial_state["logger"] = progress
        initial_state["analysis_type"] = analysis_type
        initial_state["deep_research_model"] = deep_research_model

        final_state = app.invoke(initial_state)
        logger.info("Graph execution completed successfully")

        # Save JSON as artifact for download
        if final_state.get("pysr_explanations"):
            progress.save_artifact(
                "pysr_explanations.json",
                final_state["pysr_explanations"].encode('utf-8'),
                media_type="application/json"
            )

        # Store results
        results = {
            "pysr_explanations": final_state.get("pysr_explanations"),
        }
        update_run_status(run_id, "completed", results=results)
        logger.info(f"Run {run_id} completed. Results stored.")

    except Exception as e:
        error_msg = str(e)
        update_run_status(run_id, "failed", error=error_msg)
        logger.error(f"Run {run_id} failed: {e}", exc_info=True)


def start_analysis_run(
    problem_desc: Dict[str, Any],
    csv_filename: str,
    user_id: str,
    analysis_type: str = "quick",
    deep_research_model: Optional[str] = None
) -> str:
    """
    Create a run record and start background processing.

    Args:
        problem_desc: Problem description dictionary
        csv_filename: Name of the file to analyze
        user_id: Owner's UUID as string
        analysis_type: 'quick' or 'deep'
        deep_research_model: Model for deep analysis

    Returns:
        The run UUID as string
    """
    # Create Run record in DB
    with get_db_session() as db:
        run = Run(
            problem_description=problem_desc,
            csv_filename=csv_filename,
            status="pending",
            user_id=user_id,
            analysis_type=analysis_type
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = str(run.id)

    logger.info(
        f"Starting background process for Run ID: {run_id} "
        f"(analysis_type={analysis_type}, model={deep_research_model})"
    )

    # Initialize shared memory stream for this run
    try:
        from backend.services.pysr_streaming import register_stream
        manager = get_manager()
        stream_dict = manager.dict()
        stream_dict['content'] = ""
        register_stream(run_id, stream_dict)
    except Exception as e:
        logger.error(f"Failed to initialize streaming for run {run_id}: {e}")
        stream_dict = None

    # Start worker process
    process = multiprocessing.Process(
        target=_run_worker,
        args=(run_id, problem_desc, csv_filename, analysis_type, deep_research_model, stream_dict)
    )
    process.start()

    # Register process for monitoring
    active_processes[run_id] = process

    return run_id


def check_timed_out_runs() -> None:
    """
    Check for runs that have exceeded the timeout and mark them as timed out.

    Should be called periodically to clean up stale runs.
    """
    settings = get_settings()
    timeout_hours = settings.analysis.timeout_hours

    if timeout_hours <= 0:
        return  # Timeout disabled

    cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)

    try:
        with get_db_session() as db:
            stale_runs = db.query(Run).filter(
                Run.status.in_(["running", "pending"]),
                Run.created_at < cutoff_time
            ).all()

            for run in stale_runs:
                run_id = str(run.id)
                logger.warning(
                    f"Run {run_id} has exceeded timeout of {timeout_hours} hours. "
                    "Marking as timeout."
                )
                run.status = "timeout"
                run.error = f"Analysis exceeded maximum time limit of {timeout_hours} hours"

                # Try to terminate the process if it's still tracked
                if run_id in active_processes:
                    process = active_processes[run_id]
                    if process.is_alive():
                        logger.info(f"Terminating process for run {run_id}")
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            process.kill()
                    del active_processes[run_id]

            db.commit()
    except Exception as e:
        logger.error(f"Error checking for timed out runs: {e}")
