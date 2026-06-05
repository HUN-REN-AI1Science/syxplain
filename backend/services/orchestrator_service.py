"""
Analysis orchestrator service.

Coordinates the workflow between compute backends and LLM operations,
managing the complete analysis pipeline from data ingestion to explanation.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from backend.core.config import get_compute_settings, get_slurm_settings
from backend.core.constants import RunStatus
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run
from backend.infrastructure.slurm import (
    JobState,
    SlurmBackend,
    SlurmBackendError,
    SlurmTask,
    TaskInput,
    TaskResult,
    get_slurm_backend,
)
from backend.infrastructure.slurm.client import is_quota_error
from backend.services.progress_service import ProgressTracker, _broadcast_progress_sync

logger = logging.getLogger(__name__)


def _format_user_facing_error(exc: Exception) -> str:
    """Convert an exception into a user-friendly error message."""
    try:
        import litellm

        if isinstance(exc, litellm.AuthenticationError):
            return (
                "API key authentication failed. "
                "Please check that your API key is valid and has not been revoked."
            )
        if isinstance(exc, litellm.RateLimitError):
            return (
                "API rate limit or quota exceeded. "
                "Your API account may have insufficient credits or has hit its usage limit. "
                "Please check your account balance and try again."
            )
        if isinstance(exc, litellm.BudgetExceededError):
            return (
                "API budget exceeded. "
                "Your API account has reached its spending limit. "
                "Please increase your budget or add credits and try again."
            )
        if isinstance(exc, litellm.NotFoundError):
            return (
                "The selected AI model was not found. "
                "It may have been deprecated or renamed. "
                "Please try a different model."
            )
        if isinstance(exc, litellm.APIConnectionError):
            return (
                "Could not connect to the AI service. "
                "Please check your internet connection and try again."
            )
        if isinstance(exc, litellm.Timeout):
            return (
                "The AI service request timed out. "
                "This may be due to high demand. Please try again later."
            )
    except ImportError:
        pass
    return str(exc)


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""

    compute_timeout: float = 14400.0  # 4 hours default
    poll_interval: float = 10.0
    max_retries: int = 3


@dataclass
class AnalysisContext:
    """Context for an analysis run."""

    run_id: str
    user_id: str
    problem_description: dict[str, Any]
    data: pd.DataFrame
    target_column: str
    predictor_columns: list[str]
    analysis_type: str = "quick"
    deep_research_model: str | None = None
    progress: ProgressTracker | None = None
    # User-provided API keys (not stored, only in memory)
    user_api_key: str | None = None
    user_model: str | None = None
    user_openai_key: str | None = None


class AnalysisOrchestrator:
    """
    Orchestrates the complete analysis workflow.

    Handles the coordination between:
    1. Compute-intensive tasks (SHAP, PySR) on the Slurm cluster
    2. LLM operations (config generation, explanation) on main backend

    The workflow is:
    1. Data preparation
    2. LLM generates PySR config
    3. Submit compute tasks (SHAP interactions, PySR)
    4. Wait for compute completion
    5. LLM explains results
    6. (Optional) Deep research with o4-mini
    7. Store final results
    """

    def __init__(
        self,
        backend: SlurmBackend | None = None,
        config: OrchestratorConfig | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            backend: Slurm backend to use (defaults to configured backend)
            config: Orchestrator configuration
        """
        self._backend = backend
        self._config = config or OrchestratorConfig()

    @property
    def backend(self) -> SlurmBackend:
        """Get Slurm backend (lazy initialization)."""
        if self._backend is None:
            self._backend = get_slurm_backend()
        return self._backend

    def _is_run_terminal(self, run_id: str) -> str | None:
        """Check if run is in a terminal state (failed/cancelled by worker callback).

        Returns the status string if terminal, None otherwise.
        """
        with get_db_session() as db:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run and run.status in (RunStatus.FAILED, RunStatus.CANCELLED):
                return run.status
            return None

    async def _wait_for_job(
        self,
        job_id: str,
        task_name: str,
        run_id: str,
        on_state_change=None,
    ) -> TaskResult:
        """
        Wait for a Slurm job with periodic checks for worker-reported failures.

        If a sibling worker reports an error (marking the run as failed in the DB),
        this method detects it and returns early instead of waiting for the full
        timeout. Also handles purged jobs gracefully when the run is already terminal.

        Args:
            job_id: Internal job ID
            task_name: Human-readable name (SHAP/PySR) for logging
            run_id: Run ID for DB status checks
            on_state_change: Optional callback for state transitions

        Returns:
            TaskResult with final job status
        """
        try:
            return await self.backend.wait_for_completion(
                job_id,
                poll_interval=self._config.poll_interval,
                timeout=self._config.compute_timeout,
                on_state_change=on_state_change,
            )
        except SlurmBackendError as e:
            # Check if the run was already marked as failed by a worker callback
            # (e.g., PySR failed and reported via /api/internal/error)
            terminal_status = self._is_run_terminal(run_id)
            if terminal_status == RunStatus.FAILED:
                logger.warning(
                    f"{task_name} wait failed for run {run_id}, "
                    f"but run already marked as failed by worker callback: {e}"
                )
                # Return a synthetic FAILED result — the orchestrator will
                # read the actual error from the DB
                return TaskResult(
                    job_id=job_id,
                    state=JobState.FAILED,
                    error=f"Run already failed (worker callback): {e}",
                )
            if terminal_status == RunStatus.CANCELLED:
                raise AnalysisCancelledError("Analysis cancelled by user") from e
            raise  # Re-raise for genuinely unexpected errors

    async def _submit_with_retry(
        self,
        task_input: TaskInput,
        task_name: str,
        run_id: str,
        progress: ProgressTracker,
    ) -> SlurmTask:
        """
        Submit task with automatic retry on quota errors.

        When the cluster has quota/QOS limits, job submission may fail with
        error code 2050. This method automatically retries submission after
        waiting for the configured interval.

        Args:
            task_input: Task to submit
            task_name: Human-readable task name for logging
            run_id: Run ID for cancellation checks
            progress: Progress tracker for status updates

        Returns:
            Submitted SlurmTask

        Raises:
            SlurmBackendError: If submission fails with non-quota error
            AnalysisCancelledError: If run is cancelled during retry wait
        """
        slurm_settings = get_slurm_settings()
        retry_interval = slurm_settings.retry_interval

        while True:
            try:
                return await self.backend.submit_task(task_input)
            except SlurmBackendError as e:
                # Check if it's a quota error
                if not is_quota_error(e):
                    raise  # Re-raise non-quota errors

                logger.warning(f"Quota error for {task_name}, retrying in {retry_interval}s: {e}")

                # Update progress to show waiting state
                progress.set_progress(
                    progress.current_progress,
                    status=f"Waiting for cluster resources (retry in {retry_interval}s)...",
                )

                # Wait with cancellation check (check every second)
                for _ in range(retry_interval):
                    await asyncio.sleep(1)
                    # Check if run was cancelled
                    if self._is_run_terminal(run_id) == RunStatus.CANCELLED:
                        raise AnalysisCancelledError("Analysis cancelled by user")

    async def run_analysis(self, context: AnalysisContext) -> dict[str, Any]:
        """
        Execute the complete analysis workflow.

        Args:
            context: Analysis context with input data and configuration

        Returns:
            Final analysis results

        Raises:
            OrchestratorError: If analysis fails
        """
        run_id = context.run_id
        progress = context.progress or ProgressTracker(run_id=run_id)

        logger.info(
            f"Starting orchestrated analysis for run {run_id} "
            f"(type={context.analysis_type}, backend={self.backend.name})"
        )

        try:
            # Update status to running
            self._update_run_status(run_id, RunStatus.RUNNING)
            await progress.update_progress_async("initialization", status="Initializing analysis")

            # Step 1: Data summary
            await progress.update_progress_async("data_summary", status="Analyzing dataset")
            data_summary = self._generate_data_summary(context)

            # Step 1.5: Generate feature visualizations for LLM
            await progress.update_progress_async(
                "visualization", status="Generating feature visualizations"
            )
            feature_visualizations = await asyncio.to_thread(
                self._generate_feature_visualizations, context
            )

            # Step 2: Generate PySR config using LLM
            await progress.update_progress_async(
                "pysr_config_generation", status="Generating symbolic regression configuration"
            )
            pysr_config = await self._generate_pysr_config(
                context, data_summary, visualizations_b64=feature_visualizations
            )

            # Step 3: Submit compute tasks
            await progress.update_progress_async(
                "compute_submission", status="Submitting compute tasks"
            )
            compute_results = await self._run_compute_tasks(context, pysr_config, progress)

            # Step 4: LLM explanation of results
            await progress.update_progress_async(
                "llm_explanation", status="Generating explanations"
            )
            explanations = await self._generate_explanations(context, compute_results, data_summary)

            # Step 5: Optional deep research
            if context.analysis_type == "deep" and context.deep_research_model:
                await progress.update_progress_async(
                    "deep_research", status="Performing deep research"
                )
                explanations = await self._run_deep_research(context, compute_results, explanations)

            # Step 6: Finalize and store results
            await progress.update_progress_async("finalization", status="Finalizing results")
            final_results = self._compile_final_results(context, compute_results, explanations)

            # Save artifacts (including visualizations from compute results)
            visualizations = compute_results.get("visualizations", [])
            self._save_artifacts(run_id, final_results, progress, visualizations=visualizations)

            # Mark as completed (also broadcasts via SSE)
            self._update_run_status(run_id, RunStatus.COMPLETED, results=final_results)

            logger.info(f"Analysis completed successfully for run {run_id}")
            return final_results

        except AnalysisCancelledError:
            logger.info(f"Analysis cancelled for run {run_id}")
            # Don't overwrite — cancel_run already set status to "cancelled"
            raise
        except Exception as e:
            logger.error(f"Analysis failed for run {run_id}: {e}", exc_info=True)
            error_msg = _format_user_facing_error(e)
            self._update_run_status(run_id, RunStatus.FAILED, error=error_msg)
            raise OrchestratorError(f"Analysis failed: {error_msg}") from e

    def _generate_data_summary(self, context: AnalysisContext) -> dict[str, Any]:
        """Generate a summary of the input data."""
        df = context.data
        return {
            "n_rows": len(df),
            "n_columns": len(df.columns),
            "target_column": context.target_column,
            "predictor_columns": context.predictor_columns,
            "target_stats": {
                "mean": float(df[context.target_column].mean()),
                "std": float(df[context.target_column].std()),
                "min": float(df[context.target_column].min()),
                "max": float(df[context.target_column].max()),
            },
            "column_types": {col: str(df[col].dtype) for col in context.predictor_columns},
        }

    def _generate_feature_visualizations(
        self,
        context: AnalysisContext,
    ) -> list[str]:
        """
        Generate feature vs target visualizations for LLM config generation.

        Args:
            context: Analysis context with data and column info

        Returns:
            List of base64-encoded PNG images
        """
        import base64
        import io

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        visualizations_b64 = []
        df = context.data

        for col in context.predictor_columns:
            try:
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.scatter(df[col], df[context.target_column], alpha=0.1)
                ax.set_xlabel(col)
                ax.set_ylabel(context.target_column)
                ax.set_title(f"{col} vs {context.target_column}")
                plt.tight_layout()

                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=100)
                buf.seek(0)
                visualizations_b64.append(base64.b64encode(buf.getvalue()).decode())
                plt.close(fig)
            except Exception as e:
                logger.warning(f"Failed to generate visualization for {col}: {e}")

        logger.info(f"Generated {len(visualizations_b64)} feature visualizations")
        return visualizations_b64

    async def _generate_pysr_config(
        self,
        context: AnalysisContext,
        data_summary: dict[str, Any],
        visualizations_b64: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Generate PySR configuration using LLM.

        This runs on the main backend (has LLM keys).

        Args:
            context: Analysis context
            data_summary: Data summary dictionary
            visualizations_b64: Optional list of base64-encoded visualization images

        Returns:
            PySR configuration dictionary
        """
        from backend.services.llm_service import generate_pysr_config

        try:
            # Generate enriched dataset statistics JSON for LLM
            dataset_stats_for_llm = json.dumps(
                {
                    "n_rows": data_summary.get("n_rows"),
                    "n_features": data_summary.get("n_columns", 0) - 1,
                    "predictor_columns": data_summary.get("predictor_columns", []),
                    "target_column": data_summary.get("target_column"),
                    "target_stats": data_summary.get("target_stats", {}),
                    "column_types": data_summary.get("column_types", {}),
                },
                indent=2,
            )

            # Run synchronous LLM call in thread pool to avoid blocking event loop
            config_json = await asyncio.to_thread(
                generate_pysr_config,
                project_description=json.dumps(context.problem_description),
                dataset_statistics=dataset_stats_for_llm,
                visualizations_b64=visualizations_b64 or [],
                user_api_key=context.user_api_key,
                user_model=context.user_model,
            )
            config = json.loads(config_json)
            validated = self._validate_pysr_config(config)
            logger.info(f"LLM-generated PySR config: {validated}")
            return validated
        except Exception as e:
            # User-provided keys: always fail so the user sees a clear error
            if context.user_api_key:
                raise
            logger.warning(f"LLM config generation failed, using defaults: {e}")
            # Server keys: return default config (niterations=None lets worker auto-estimate)
            return {
                "niterations": None,
                "populations": 15,
                "binary_operators": ["+", "-", "*", "/"],
                "unary_operators": ["exp", "log", "sqrt", "abs"],
                "maxsize": 20,
                "maxdepth": 10,
            }

    def _validate_pysr_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and clamp LLM-generated PySR search parameters to safe ranges.

        Non-integer values are set to None (triggers worker defaults).

        Args:
            config: Raw config dict from LLM

        Returns:
            Config dict with clamped/validated values
        """
        clamp_ranges = {
            "niterations": (50, 10000),
            "maxsize": (7, 50),
            "maxdepth": (4, 20),
        }

        for key, (lo, hi) in clamp_ranges.items():
            val = config.get(key)
            if val is None:
                continue
            if not isinstance(val, int):
                # Try to convert string/float to int, otherwise null out
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    logger.warning(
                        f"PySR config: {key}={config[key]!r} is not an integer, setting to null"
                    )
                    config[key] = None
                    continue
            if val < lo or val > hi:
                clamped = max(lo, min(hi, val))
                logger.warning(f"PySR config: clamping {key}={val} to {clamped} (range {lo}-{hi})")
                val = clamped
            config[key] = val

        # Ensure maxdepth <= maxsize when both are set
        maxdepth = config.get("maxdepth")
        maxsize = config.get("maxsize")
        if isinstance(maxdepth, int) and isinstance(maxsize, int) and maxdepth > maxsize:
            logger.warning(
                f"PySR config: maxdepth ({maxdepth}) > maxsize ({maxsize}), clamping maxdepth"
            )
            config["maxdepth"] = maxsize

        return config

    async def _run_compute_tasks(
        self,
        context: AnalysisContext,
        pysr_config: dict[str, Any],
        progress: ProgressTracker,
    ) -> dict[str, Any]:
        """
        Submit and monitor compute tasks on the backend.

        Runs SHAP and PySR tasks, possibly in parallel depending
        on available resources.
        """
        compute_settings = get_compute_settings()
        results = {}

        # Report HPC connection phase (user-friendly)
        await progress.update_progress_async(
            "hpc_connecting", status="Connecting to computing cluster"
        )

        # Build task inputs
        shap_task_input = TaskInput(
            task_type="shap",
            run_id=context.run_id,
            input_data={
                "data": context.data[[context.target_column, *context.predictor_columns]].to_dict(
                    orient="split"
                ),
                "target_column": context.target_column,
                "predictor_columns": context.predictor_columns,
                "generate_visualizations": True,
            },
            callback_url=compute_settings.worker_callback_url,
            callback_token=compute_settings.worker_callback_token,
        )

        pysr_task_input = TaskInput(
            task_type="pysr",
            run_id=context.run_id,
            input_data={
                "data": context.data[[context.target_column, *context.predictor_columns]].to_dict(
                    orient="split"
                ),
                "target_column": context.target_column,
                "predictor_columns": context.predictor_columns,
                "config": pysr_config,
            },
            callback_url=compute_settings.worker_callback_url,
            callback_token=compute_settings.worker_callback_token,
        )

        # Submit tasks with retry on quota errors
        shap_job = await self._submit_with_retry(shap_task_input, "SHAP", context.run_id, progress)
        logger.info(f"SHAP task submitted as job {shap_job.job_id}")

        pysr_job = await self._submit_with_retry(pysr_task_input, "PySR", context.run_id, progress)
        logger.info(f"PySR task submitted as job {pysr_job.job_id}")

        # Report queued phase (user-friendly - jobs are submitted, waiting in queue)
        await progress.update_progress_async("hpc_queued", status="Jobs queued for processing")

        # Store job IDs in database for cancellation
        self._store_slurm_job_ids(
            context.run_id,
            {
                "shap_job_id": shap_job.job_id,
                "pysr_job_id": pysr_job.job_id,
            },
        )

        # Wait for completion (can run in parallel on cluster)
        # Track whether we've reported the hpc_starting phase
        hpc_started_reported = False

        def on_job_state_change(old_state, new_state, status):
            """Report hpc_starting when first job transitions to RUNNING."""
            nonlocal hpc_started_reported
            if not hpc_started_reported and new_state == JobState.RUNNING:
                progress.update_progress(
                    "hpc_starting", status="Resources allocated, starting compute"
                )
                hpc_started_reported = True

        shap_status = await self._wait_for_job(
            shap_job.job_id, "SHAP", context.run_id, on_job_state_change
        )
        pysr_status = await self._wait_for_job(
            pysr_job.job_id, "PySR", context.run_id, on_job_state_change
        )

        # Check for cancellation first, then failures
        if shap_status.state == JobState.CANCELLED or pysr_status.state == JobState.CANCELLED:
            raise AnalysisCancelledError("Analysis cancelled by user")

        if shap_status.state != JobState.COMPLETED:
            raise OrchestratorError(f"SHAP task failed: {shap_status.error}")

        if pysr_status.state != JobState.COMPLETED:
            raise OrchestratorError(f"PySR task failed: {pysr_status.error}")

        # Retrieve results
        shap_result = await self.backend.get_task_result(shap_job.job_id)
        pysr_result = await self.backend.get_task_result(pysr_job.job_id)

        results["shap"] = shap_result
        results["pysr"] = pysr_result

        # Extract visualizations from SHAP results
        results["visualizations"] = shap_result.get("visualizations", [])
        logger.info(
            f"Compute tasks completed for run {context.run_id}, "
            f"{len(results['visualizations'])} visualizations generated"
        )

        return results

    async def _generate_explanations(
        self,
        context: AnalysisContext,
        compute_results: dict[str, Any],
        data_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate LLM explanations for the results.

        This runs on the main backend (has LLM keys).
        """
        from backend.services.llm_service import generate_equation_explanation

        try:
            # Format equations for the LLM service
            equations = compute_results.get("pysr", {}).get("equations", [])
            data_spec = {
                "equation": [eq.get("equation", "") for eq in equations],
                "loss": [eq.get("loss", 0) for eq in equations],
                "complexity": [eq.get("complexity", 0) for eq in equations],
            }

            # Run synchronous LLM call in thread pool to avoid blocking event loop
            explanations = await asyncio.to_thread(
                generate_equation_explanation,
                project_spec_json=json.dumps(context.problem_description),
                data_spec_json=json.dumps(data_spec),
                deep_research_context=None,
                user_api_key=context.user_api_key,
                user_model=context.user_model,
            )
            return explanations
        except Exception as e:
            # User-provided keys: always fail so the user sees a clear error
            if context.user_api_key:
                raise
            logger.error(f"Explanation generation failed: {e}")
            # Server keys: return partial results with error noted
            return {
                "error": str(e),
                "equations": compute_results.get("pysr", {}).get("equations", []),
            }

    async def _run_deep_research(
        self,
        context: AnalysisContext,
        compute_results: dict[str, Any],
        explanations: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run deep research using o4-mini.

        This runs on the main backend (has LLM keys).
        """
        from backend.services.llm_service import (
            deep_research_equations,
            generate_equation_explanation,
        )

        try:
            # Get features from problem description
            features_dict = context.problem_description.get("features", {})

            if not features_dict:
                logger.warning("No features defined for deep research")
                return explanations

            # Run synchronous LLM calls in thread pool to avoid blocking event loop
            # Deep research uses OpenAI (o4-mini-deep-research), so pass user_openai_key
            deep_result = await asyncio.to_thread(
                deep_research_equations,
                features_dict=features_dict,
                model_name=context.deep_research_model,
                user_api_key=context.user_openai_key,
            )

            # Re-generate explanations with deep research context
            equations = compute_results.get("pysr", {}).get("equations", [])
            data_spec = {
                "equation": [eq.get("equation", "") for eq in equations],
                "loss": [eq.get("loss", 0) for eq in equations],
                "complexity": [eq.get("complexity", 0) for eq in equations],
            }

            enhanced_explanations = await asyncio.to_thread(
                generate_equation_explanation,
                project_spec_json=json.dumps(context.problem_description),
                data_spec_json=json.dumps(data_spec),
                deep_research_context=deep_result,
                user_api_key=context.user_api_key,
                user_model=context.user_model,
            )

            return enhanced_explanations
        except Exception as e:
            # User-provided keys: always fail so the user sees a clear error
            if context.user_api_key or context.user_openai_key:
                raise
            logger.error(f"Deep research failed: {e}")
            # Server keys: return previous explanations without deep research
            return explanations

    def _compile_final_results(
        self,
        context: AnalysisContext,
        compute_results: dict[str, Any],
        explanations: dict[str, Any],
    ) -> dict[str, Any]:
        """Compile all results into final output format."""
        pysr_results = compute_results.get("pysr", {})
        scatter_data = pysr_results.get("scatter_data", {})

        # Merge scatter_data into equations in explanations (matching legacy behavior)
        if "equations" in explanations and scatter_data:
            matched_count = 0
            for eq in explanations["equations"]:
                eq_str = eq.get("equation", "")
                if eq_str in scatter_data:
                    eq["scatter_data"] = scatter_data[eq_str]
                    matched_count += 1
            logger.info(f"Merged scatter data for {matched_count} equations")

        return {
            "equations": pysr_results.get("equations", []),
            "best_equation": pysr_results.get("best_equation"),
            "interactions": compute_results.get("shap", {}).get("interactions", []),
            "top_features": compute_results.get("shap", {}).get("top_features", []),
            "explanations": explanations,
            "scatter_data": scatter_data,  # Also include at top level for backwards compatibility
            "analysis_type": context.analysis_type,
            "compute_backend": self.backend.name,
            "completed_at": datetime.utcnow().isoformat(),
        }

    def _save_artifacts(
        self,
        run_id: str,
        results: dict[str, Any],
        progress: ProgressTracker,
        visualizations: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        Save result artifacts including visualizations.

        Args:
            run_id: Run identifier
            results: Results dictionary (will have visualizations stripped for JSON)
            progress: Progress tracker for saving artifacts
            visualizations: List of visualization dicts with filename, content_b64, type
        """
        import base64

        try:
            # Create a copy of results without embedded visualizations (too large for JSON)
            results_for_json = {k: v for k, v in results.items() if k != "visualizations"}
            results_json = json.dumps(results_for_json, indent=2).encode("utf-8")
            progress.save_artifact(
                "pysr_explanations.json", results_json, media_type="application/json"
            )
        except Exception as e:
            logger.error(f"Failed to save JSON artifact for {run_id}: {e}")

        # Save visualization images
        if visualizations:
            for viz in visualizations:
                try:
                    filename = viz.get("filename", "visualization.png")
                    content_b64 = viz.get("content_b64", "")
                    if content_b64:
                        content_bytes = base64.b64decode(content_b64)
                        progress.save_artifact(filename, content_bytes, media_type="image/png")
                except Exception as e:
                    logger.warning(f"Failed to save visualization {viz.get('filename')}: {e}")

            logger.info(f"Saved {len(visualizations)} visualizations for run {run_id}")

    def _store_slurm_job_ids(self, run_id: str, job_ids: dict[str, str]) -> None:
        """
        Store Slurm job IDs in database for cancellation support.

        Args:
            run_id: Run identifier
            job_ids: Dictionary with shap_job_id and pysr_job_id
        """
        try:
            with get_db_session() as db:
                run = db.query(Run).filter(Run.id == run_id).first()
                if run:
                    run.slurm_job_ids = job_ids
                    db.commit()
                    logger.info(f"Stored Slurm job IDs for run {run_id}: {job_ids}")
        except Exception as e:
            logger.error(f"Failed to store Slurm job IDs for {run_id}: {e}")

    def _update_run_status(
        self,
        run_id: str,
        status: str,
        results: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update run status in database and broadcast terminal states via SSE."""
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
                    if status == RunStatus.COMPLETED:
                        run.progress = 100
                    db.commit()

                    # Broadcast terminal states via SSE so clients see completion/failure
                    if RunStatus.is_terminal(status):
                        _broadcast_progress_sync(
                            run_id=run_id,
                            progress=run.progress or 0,
                            status=status,
                            error=error,
                        )
        except Exception as e:
            logger.error(f"Failed to update run status for {run_id}: {e}")


class OrchestratorError(Exception):
    """Error during orchestration."""

    pass


class AnalysisCancelledError(OrchestratorError):
    """Raised when the analysis is cancelled by the user."""

    pass


async def run_orchestrated_analysis(
    run_id: str,
    problem_desc: dict[str, Any],
    data: pd.DataFrame,
    user_id: str,
    analysis_type: str = "quick",
    deep_research_model: str | None = None,
    user_api_key: str | None = None,
    user_model: str | None = None,
    user_openai_key: str | None = None,
) -> dict[str, Any]:
    """
    Convenience function to run analysis with orchestrator.

    Args:
        run_id: UUID of the run
        problem_desc: Problem description dictionary
        data: Input DataFrame
        user_id: Owner user ID
        analysis_type: 'quick' or 'deep'
        deep_research_model: Model for deep analysis
        user_api_key: Optional user-provided Gemini API key
        user_model: Optional user-specified Gemini model
        user_openai_key: Optional user-provided OpenAI API key for deep research

    Returns:
        Analysis results
    """
    target_column = problem_desc["target_variable"]
    predictor_columns = list(problem_desc["features"].keys())

    # Filter to numeric predictors
    numeric_predictors = [
        col
        for col in predictor_columns
        if col in data.columns and pd.api.types.is_numeric_dtype(data[col])
    ]

    context = AnalysisContext(
        run_id=run_id,
        user_id=user_id,
        problem_description=problem_desc,
        data=data,
        target_column=target_column,
        predictor_columns=numeric_predictors,
        analysis_type=analysis_type,
        deep_research_model=deep_research_model,
        user_api_key=user_api_key,
        user_model=user_model,
        user_openai_key=user_openai_key,
    )

    orchestrator = AnalysisOrchestrator()
    return await orchestrator.run_analysis(context)
