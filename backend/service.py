import sys
import os
import json
import time
import pandas as pd
import multiprocessing
import logging
import io
from typing import Dict, Any
from datetime import datetime, timedelta

# Add parent directory to path to import syxplain modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import StepLogger
from backend.database import SessionLocal, Run as DbRun, File as DbFile, engine

logger = logging.getLogger(__name__)

# Global registry for active processes
active_processes: Dict[str, multiprocessing.Process] = {}

def cleanup_processes():
    """Checks active processes and cleans up finished ones."""
    finished_run_ids = []
    for run_id, process in active_processes.items():
        if not process.is_alive():
            process.join()  # Ensure resources are released
            finished_run_ids.append(run_id)
            logger.info(f"Process for run {run_id} has finished and was joined.")

    for run_id in finished_run_ids:
        del active_processes[run_id]

def update_run_status(run_id: str, status: str, results: Dict[str, Any] = None, error: str = None, progress: int = None):
    """Updates the run status in the database."""
    db = None
    try:
        db = SessionLocal()
        run = db.query(DbRun).filter(DbRun.id == run_id).first()
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
    finally:
        if db:
            db.close()

def _run_worker(run_id: str, problem_desc: Dict[str, Any], csv_filename: str, analysis_type: str = "quick", deep_research_model: str = None):
    from logger import configure_debug_logging, configure_logging
    configure_logging()
    configure_debug_logging()

    # Import syxplain_lib here to ensure Julia is initialized ONLY in this worker process
    from syxplain_lib import State, run_syxplain

    # Dispose of the engine to ensure fresh connections in this process
    engine.dispose()

    logger.info(f"Worker process started for Run ID: {run_id}")
    try:
        update_run_status(run_id, "running")

        # Load data from DB
        db = None
        try:
            db = SessionLocal()
            db_file = db.query(DbFile).filter(DbFile.filename == csv_filename).order_by(DbFile.created_at.desc()).first()
            if not db_file:
                raise Exception(f"File {csv_filename} not found in database")

            logger.info(f"Loading data for {csv_filename} from DB")
            sample_data = pd.read_csv(io.BytesIO(db_file.content))
        finally:
            if db:
                db.close()

        # Prepare state
        problem_description_src = json.dumps(problem_desc, indent=2)

        # Initialize custom logger with run_id
        run_logger = StepLogger(run_id=run_id)

        def entry_point(state: State) -> State:
            logger.info("Executing entry_point node")
            state["logger"] = run_logger
            state["logger"].log_step("initialization", {"status": "Initializing analysis", "rows": len(sample_data), "columns": len(sample_data.columns)})

            state["data"] = sample_data
            state["problem_description_src"] = problem_description_src
            state["target_column"] = problem_desc["target_variable"]

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

        # Run the graph
        from syxplain_lib import data_summary, llm_pysr_config_generator, pysr_with_generated_config, explain_pysr_equations, deep_research_node
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
        initial_state["logger"] = run_logger
        initial_state["analysis_type"] = analysis_type
        initial_state["deep_research_model"] = deep_research_model

        final_state = app.invoke(initial_state)
        logger.info("Graph execution completed successfully")

        # Save JSON as artifact for download
        if final_state.get("pysr_explanations"):
            run_logger.log_artifact(
                "pysr_explanations.json",
                final_state["pysr_explanations"].encode('utf-8'),
                media_type="application/json"
            )

        # Store results
        # We don't have a run_dir anymore, but we can store the explanations directly
        results = {
            "pysr_explanations": final_state.get("pysr_explanations"),
            # Add other relevant results here if needed
        }
        update_run_status(run_id, "completed", results=results)
        logger.info(f"Run {run_id} completed. Results stored.")

    except Exception as e:
        error_msg = str(e)
        update_run_status(run_id, "failed", error=error_msg)
        logger.error(f"Run {run_id} failed: {e}", exc_info=True)

def start_run(problem_desc: Dict[str, Any], csv_filename: str, api_key: str, api_base: str = None, model_name: str = None, user_id: str = None, analysis_type: str = "quick", deep_research_model: str = None) -> str:
    # Create Run record in DB
    db = None
    try:
        db = SessionLocal()
        run = DbRun(
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
    finally:
        if db:
            db.close()

    logger.info(f"Starting background process for Run ID: {run_id} (analysis_type={analysis_type}, model={deep_research_model})")
    # Use multiprocessing.Process instead of threading.Thread
    # Note: API credentials are inherited from parent process environment variables
    process = multiprocessing.Process(target=_run_worker, args=(run_id, problem_desc, csv_filename, analysis_type, deep_research_model))
    process.start()

    # Register process for monitoring
    active_processes[run_id] = process

    return run_id

def get_run_status(run_id: str) -> Dict[str, Any]:
    db = None
    try:
        db = SessionLocal()
        run = db.query(DbRun).filter(DbRun.id == run_id).first()
        if run:
            return {
                "status": run.status,
                "progress": run.progress or 0,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "results": run.results,
                "error": run.error
            }
        return {"status": "not_found", "progress": 0}
    except Exception as e:
        logger.error(f"Error retrieving run status for {run_id}: {e}")
        return {"status": "error", "progress": 0, "error": "Could not retrieve status from database"}
    finally:
        if db:
            db.close()


def check_timed_out_runs():
    """Check for runs that have exceeded the timeout and mark them as timed out."""
    timeout_hours = float(os.environ.get("ANALYSIS_TIMEOUT_HOURS", "24"))
    if timeout_hours <= 0:
        return  # Timeout disabled

    db = None
    try:
        db = SessionLocal()
        cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)

        # Find running or pending runs that started before cutoff
        stale_runs = db.query(DbRun).filter(
            DbRun.status.in_(["running", "pending"]),
            DbRun.created_at < cutoff_time
        ).all()

        for run in stale_runs:
            run_id = str(run.id)
            logger.warning(f"Run {run_id} has exceeded timeout of {timeout_hours} hours. Marking as timeout.")
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
    finally:
        if db:
            db.close()
