"""
Analysis orchestrator service.

Coordinates the workflow between compute backends and LLM operations,
managing the complete analysis pipeline from data ingestion to explanation.
"""

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from backend.core.config import (
    get_compute_settings,
    get_discovery_settings,
    get_slurm_settings,
)
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
from backend.services.discovery.session import (
    ALLOWED_BINARY,
    ALLOWED_UNARY,
    DiscoveryBudget,
    DiscoverySession,
)
from backend.services.progress_service import ProgressTracker, _broadcast_progress_sync

logger = logging.getLogger(__name__)


_DSPY_ERROR_MESSAGES = {
    "LMAuthError": "API key authentication failed. Please check that your API key is valid and has not been revoked.",
    "LMBillingError": "API budget exceeded. Your API account has reached its spending limit. Please add credits and try again.",
    "LMRateLimitError": "API rate limit or quota exceeded. Please check your account limits and try again later.",
    "LMUnsupportedModelError": "The selected AI model was not found or is not supported. Please try a different model.",
    "LMTimeoutError": "The AI service request timed out. This may be due to high demand. Please try again later.",
    "LMTransportError": "Could not connect to the AI service. Please check the connection and try again.",
    "LMServerError": "The AI service returned a server error. Please try again later.",
}


def _format_user_facing_error(exc: BaseException) -> str:
    """Convert an exception into a user-friendly error message."""
    for cls in type(exc).__mro__:  # DSPy >= 3.4 wraps provider errors in its own types
        if cls.__name__ in _DSPY_ERROR_MESSAGES:
            return _DSPY_ERROR_MESSAGES[cls.__name__]
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
    return str(exc) or type(exc).__name__


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
    1. The discovery agent and classic-model fitting (in this process)
    2. PySR searches on the Slurm cluster (launched by the orchestrator and the agent)
    3. LLM operations (config generation, explanation) on main backend

    The workflow is:
    1. Data preparation
    2. LLM generates the config of a baseline PySR search, which is submitted
    3. Discovery agent fits classic laws, diagnoses failures and steers more PySR searches
    4. Every model is scored on held-out data
    5. LLM explains results (with the agent's notebook as context)
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
            task_name: Human-readable name (e.g. pysr_2) for logging
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

            # Step 3: Agentic discovery (baseline PySR search + agent-driven loop)
            discovery_results = await self._run_discovery(context, pysr_config, progress)
            warnings = discovery_results.pop("warnings", [])

            # The discovery brief is complete on its own: persist it before narration,
            # so a failing explanation step can never lose it.
            await asyncio.to_thread(self._store_results, run_id, discovery_results)

            # Step 4: Narration (best-effort for every key type)
            explanations = await self._narrate(context, discovery_results, progress, warnings)

            # Step 5: Finalize and store results
            await progress.update_progress_async("finalization", status="Finalizing results")
            final_results = self._compile_final_results(
                context, discovery_results, explanations, warnings
            )

            visualizations = [
                {"filename": f"feature_{i + 1}_vs_target.png", "content_b64": b64}
                for i, b64 in enumerate(feature_visualizations)
            ]
            self._save_artifacts(run_id, final_results, progress, visualizations=visualizations)

            # Mark as completed (also broadcasts via SSE)
            if not self._update_run_status(run_id, RunStatus.COMPLETED, results=final_results):
                self._update_run_status(run_id, RunStatus.FAILED, error="Failed to store results")
                raise OrchestratorError("Failed to store results")

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

    def _discovery_budget(self, analysis_type: str) -> DiscoveryBudget:
        settings = get_discovery_settings()
        limits = settings.for_type(analysis_type)
        budget = DiscoveryBudget(
            max_iters=limits["max_iters"],
            max_pysr_runs=limits["max_pysr_runs"],
            max_concurrent_pysr=limits["max_concurrent_pysr"],
            wall_clock_s=limits["wall_clock_s"],
            pysr_timeout_s=limits["pysr_timeout_s"],
            max_tool_calls=limits["max_tool_calls"],
        )
        if not settings.enabled:
            budget.max_pysr_runs = 1  # baseline search only
        return budget

    def _discovery_project(
        self, context: AnalysisContext, session: DiscoverySession
    ) -> dict[str, Any]:
        """Project description for the agent, with features keyed by their expression alias."""
        desc = context.problem_description
        features = desc.get("features", {}) or {}
        return {
            "project_description": desc.get("project_description", ""),
            "target": {"alias": session.target_alias, "column": context.target_column},
            "features": {
                alias: {
                    "column": session.column_of[alias],
                    "description": features.get(session.column_of[alias], ""),
                    "kind": session.kinds.get(alias, "continuous"),
                }
                for alias in session.features
            },
            "excluded_columns": session.excluded_columns,
        }

    async def _run_discovery(
        self,
        context: AnalysisContext,
        pysr_config: dict[str, Any],
        progress: ProgressTracker,
    ) -> dict[str, Any]:
        """
        Agentic equation discovery (the run controller's EXPLORE..SELECT phases).

        LAUNCH: the baseline PySR search (and, in deep mode, the literature scout) start
        first so the Slurm queue and the research model overlap with profiling and the
        agent. PROFILE runs in a separate process. EXPLORE is the agent's budget. SETTLE
        waits for searches, RECONCILE makes the agent's report consistent with what
        finished, and SELECT/PERSIST build the brief. Whatever happens to the agent, the
        run ends with the baseline equations plus classic baselines; on any failure or
        cancellation every launched search is cancelled.
        """
        from backend.api.sse.connection_manager import get_connection_manager
        from backend.services.discovery.literature import literature_features, run_literature
        from backend.services.discovery.reconcile import reconcile
        from backend.services.discovery.report import build_results

        settings = get_discovery_settings()
        budget = self._discovery_budget(context.analysis_type)
        manager = get_connection_manager()
        warnings: list[dict[str, str]] = []

        async def on_event(event: dict[str, Any]) -> None:
            await manager.broadcast_event(context.run_id, event)

        descriptions = context.problem_description.get("features", {}) or {}
        launcher = _SlurmSearchLauncher(self, context, progress)
        session = await asyncio.to_thread(
            DiscoverySession,
            context.data,
            context.target_column,
            context.predictor_columns,
            budget,
            launcher,
            on_event,
            descriptions=descriptions,
            sparse_column_threshold=settings.sparse_column_threshold,
            max_categorical_levels=settings.max_categorical_levels,
        )

        try:
            # LAUNCH
            await progress.update_progress_async(
                "compute_submission", status="Submitting baseline symbolic regression search"
            )
            baseline_features = session.continuous_features or session.features
            await session.start_search(
                features=baseline_features,
                unary_operators=[
                    u for u in pysr_config.get("unary_operators") or [] if u in ALLOWED_UNARY
                ],
                binary_operators=[
                    b for b in pysr_config.get("binary_operators") or [] if b in ALLOWED_BINARY
                ]
                or ["+", "-", "*", "/"],
                maxsize=pysr_config.get("maxsize"),
                niterations=pysr_config.get("niterations"),
                rationale="Baseline: all continuous features, operators chosen from the feature plots",
                enforce_budget=False,
            )
            if self._wants_literature(context):
                features_for_lit = literature_features(
                    session,
                    descriptions,
                    context.problem_description.get("project_description", ""),
                )
                session.literature_task = asyncio.create_task(
                    run_literature(session, self._literature_lookup(context, features_for_lit))
                )

            # PROFILE (separate process; not charged to the agent's budget)
            await session.ensure_profile()
            session.reset_clock()

            # EXPLORE
            agent_report: dict[str, Any] | None = None
            agent_error: str | None = None
            lm = None
            if settings.enabled:
                agent_report, agent_error, lm = await self._run_agent(
                    context, session, budget, progress, settings.model_name
                )
                if agent_error:
                    warnings.append({"stage": "agent", "message": agent_error})
            self._raise_if_cancelled(context, session)

            # Classic baselines must exist even when the agent was off or failed early.
            if sum(1 for m in session.snapshot() if m.kind != "symbolic") < 3:
                await session.emit("agent", "Screening the classic function catalog")
                await asyncio.to_thread(session.auto_screen)

            # SETTLE
            pending = [s.search_id for s in session.searches.values() if not s.done]
            await progress.update_progress_async(
                "discovery_agent",
                status=f"Waiting for {', '.join(pending)}" if pending else "Collecting results",
            )
            await session.ensure_result(
                grace_s=min(session.remaining_s + 300, 1800),
                max_wait_s=settings.first_result_timeout_s,
            )
            self._raise_if_cancelled(context, session)
            if session.literature_task is not None:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(session.literature_task), timeout=600)
                if not session.literature_task.done():
                    session.literature_task.cancel()
                    warnings.append(
                        {
                            "stage": "literature",
                            "message": "Literature search did not finish in time",
                        }
                    )
                laws = session.known_laws or {}
                if laws.get("status") in ("empty", "failed"):
                    warnings.append(
                        {
                            "stage": "literature",
                            "message": "No published laws were found for these variables"
                            if laws.get("status") == "empty"
                            else f"Literature search failed: {laws.get('error')}",
                        }
                    )

            # RECONCILE
            if agent_report is not None:
                review = None
                if (
                    settings.review_steps > 0
                    and lm is not None
                    and agent_report.get("ended") in ("finish", "steps", "time")
                ):
                    review = self._review_fn(context, session, lm, settings.review_steps)
                agent_report = await reconcile(session, agent_report, review)

            await progress.update_progress_async("discovery_wrapup", status="Scoring models")
            completed = [s for s in session.searches.values() if s.status == "completed"]
            if not completed:
                errors = "; ".join(
                    f"{s.search_id}: {s.error or s.status}" for s in session.searches.values()
                )
                if not any(not m.error for m in session.snapshot()):
                    raise OrchestratorError(f"PySR task failed: {errors}")
                session.note(
                    "data_issue",
                    f"All symbolic regression searches failed ({errors}); results contain classic "
                    "models only",
                )
                warnings.append({"stage": "symbolic_regression", "message": errors[:500]})

            # SELECT + PERSIST
            results = await asyncio.to_thread(build_results, session, agent_report, agent_error)
            results["warnings"] = warnings
            await progress.update_progress_async(
                "final_scoring", status="Models scored and selected"
            )
            logger.info(
                f"Discovery finished for run {context.run_id}: {len(session.models)} models, "
                f"{len(session.searches)} searches, {len(results['equations'])} equations reported, "
                f"headline {results['discovery']['selection']['headline_model_id']}"
            )
            return results
        except BaseException:
            session.cancelled = True
            if session.literature_task is not None:
                session.literature_task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.shield(session.cancel_all())
            raise

    def _raise_if_cancelled(self, context: AnalysisContext, session: DiscoverySession) -> None:
        if session.cancelled or self._is_run_terminal(context.run_id) == RunStatus.CANCELLED:
            session.cancelled = True
            raise AnalysisCancelledError("Analysis cancelled by user")

    async def _run_agent(
        self,
        context: AnalysisContext,
        session: DiscoverySession,
        budget: DiscoveryBudget,
        progress: ProgressTracker,
        model_name: str,
    ) -> tuple[dict[str, Any] | None, str | None, Any]:
        """
        Run the discovery agent. Any agent failure (LM setup, LLM errors, timeout) is
        returned as an error string so the run continues with the fallback path.

        Returns:
            (report, error, lm)
        """
        from backend.services.discovery.agent import fallback_report, run_discovery_agent
        from backend.services.discovery.tools import build_tools

        async def failed(e: BaseException, message: str | None = None):
            error = message or _format_user_facing_error(e)
            logger.error(f"Discovery agent failed for run {context.run_id}: {e!r}")
            await session.emit(
                "agent", f"Agent stopped with an error; continuing with fallback ({error[:120]})"
            )
            report = fallback_report(session, "the agent stopped with an error")
            report["ended"] = "llm_error"
            return report, error

        try:
            lm = self._discovery_lm(context, model_name)
            tools = build_tools(session, literature_enabled=self._wants_literature(context))
        except Exception as e:
            report, error = await failed(e)
            return report, error, None

        agent_task = asyncio.create_task(
            run_discovery_agent(
                session,
                tools,
                lm,
                self._discovery_project(context, session),
                max_iters=budget.max_iters,
            )
        )
        ticker = asyncio.create_task(self._watch_discovery(session, progress, agent_task))
        try:
            report = await asyncio.wait_for(
                asyncio.shield(agent_task), timeout=budget.wall_clock_s + 600
            )
            return report, None, lm
        except asyncio.CancelledError:
            agent_task.cancel()
            if session.cancelled or self._is_run_terminal(context.run_id) == RunStatus.CANCELLED:
                session.cancelled = True
                raise AnalysisCancelledError("Analysis cancelled by user") from None
            raise
        except (asyncio.TimeoutError, TimeoutError) as e:
            agent_task.cancel()
            report, error = await failed(e, "The discovery agent exceeded its time budget")
            return report, error, lm
        except Exception as e:
            agent_task.cancel()
            report, error = await failed(e)
            return report, error, lm
        finally:
            ticker.cancel()

    def _review_fn(self, context: AnalysisContext, session: DiscoverySession, lm, steps: int):
        """Read-only review pass over late searches (a few extra minutes of agent time)."""
        from backend.services.discovery.agent import run_review
        from backend.services.discovery.tools import build_tools

        async def review(report: dict[str, Any], late: list[str]) -> dict[str, Any]:
            session.budget.wall_clock_s = session.elapsed_s + 300
            session.budget.max_tool_calls = session.tool_calls + steps * 2
            return await asyncio.wait_for(
                run_review(
                    session,
                    build_tools(session),
                    lm,
                    self._discovery_project(context, session),
                    report,
                    late,
                    max_iters=steps,
                ),
                timeout=420,
            )

        return review

    def _discovery_lm(self, context: AnalysisContext, model_name: str):
        from backend.infrastructure.llm.client import create_dspy_model

        return create_dspy_model(
            model_name=model_name or None,
            user_api_key=context.user_api_key,
            user_model=context.user_model,
            num_retries=6,
        )

    def _wants_literature(self, context: AnalysisContext) -> bool:
        return context.analysis_type == "deep" and bool(context.deep_research_model)

    def _literature_lookup(self, context: AnalysisContext, features: dict[str, str]):
        """Deep mode: one call to the research model (features keyed by alias, with the target)."""
        from backend.services.llm_service import deep_research_equations

        async def lookup() -> dict[str, Any]:
            return await asyncio.to_thread(
                deep_research_equations,
                features_dict=features,
                model_name=context.deep_research_model,
                user_api_key=context.user_openai_key,
            )

        return lookup

    async def _watch_discovery(
        self,
        session: DiscoverySession,
        progress: ProgressTracker,
        agent_task: asyncio.Task,
    ) -> None:
        """Advance the progress bar with the agent's time budget and watch for cancellation."""
        start, end = 10, 71
        try:
            while not agent_task.done():
                await asyncio.sleep(10)
                try:
                    status = await asyncio.to_thread(self._is_run_terminal, progress.run_id)
                    if status == RunStatus.CANCELLED:
                        session.cancelled = True
                        agent_task.cancel()
                        return
                    frac = min(1.0, session.elapsed_s / max(session.budget.wall_clock_s, 1.0))
                    await progress.set_progress_async(int(start + frac * (end - start)))
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # a DB hiccup must not stop cancellation checks
                    logger.warning(f"Discovery watcher tick failed: {e}")
        except asyncio.CancelledError:
            pass

    async def _narrate(
        self,
        context: AnalysisContext,
        discovery_results: dict[str, Any],
        progress: ProgressTracker,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Explanation (and, in deep mode, literature-grounded explanation). Best-effort for
        every key type: the discovery brief is complete without it, so a failure becomes
        a warning, never a failed run.
        """
        from backend.services.discovery.literature import deep_research_context

        deep_ctx = None
        if self._wants_literature(context):
            await progress.update_progress_async("deep_research", status="Integrating literature")
            deep_ctx = deep_research_context(discovery_results["discovery"].get("literature"))
        await progress.update_progress_async("llm_explanation", status="Generating explanations")
        try:
            return await self._generate_explanations(context, discovery_results, deep_ctx)
        except (asyncio.CancelledError, AnalysisCancelledError):
            raise
        except Exception as e:
            message = _format_user_facing_error(e)
            logger.error(f"Explanation failed for run {context.run_id}: {e!r}")
            warnings.append({"stage": "explanation", "message": message})
            return {"error": message, "equations": discovery_results.get("equations", [])}

    async def _generate_explanations(
        self,
        context: AnalysisContext,
        discovery_results: dict[str, Any],
        deep_research_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate LLM explanations for the discovery brief (raises on failure)."""
        from backend.services.discovery.report import explanation_data_spec
        from backend.services.llm_service import generate_equation_explanation

        data_spec = explanation_data_spec(discovery_results)
        # Run synchronous LLM call in thread pool to avoid blocking event loop
        return await asyncio.to_thread(
            generate_equation_explanation,
            project_spec_json=json.dumps(context.problem_description),
            data_spec_json=json.dumps(data_spec),
            deep_research_context=deep_research_context,
            user_api_key=context.user_api_key,
            user_model=context.user_model,
        )

    def _compile_final_results(
        self,
        context: AnalysisContext,
        discovery_results: dict[str, Any],
        explanations: dict[str, Any],
        warnings: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Compile all results into final output format (provenance joined by model_id)."""
        from backend.services.discovery.report import json_safe, merge_explanations

        equations = discovery_results.get("equations", [])
        if "error" not in explanations:
            explanations, matched = merge_explanations(explanations, equations)
            if matched < len(equations):
                logger.warning(
                    f"Explanation covered {matched} of {len(equations)} equations; the rest are "
                    "shown without narration"
                )
        return json_safe(
            {
                "equations": equations,
                "best_equation": discovery_results.get("best_equation"),
                "explanations": explanations,
                "scatter_data": discovery_results.get("scatter_data", {}),
                "discovery": discovery_results.get("discovery"),
                "warnings": warnings or [],
                "analysis_type": context.analysis_type,
                "compute_backend": self.backend.name,
                "completed_at": datetime.utcnow().isoformat(),
            }
        )

    def _store_results(self, run_id: str, results: dict[str, Any]) -> None:
        """Persist intermediate results while the run is still RUNNING."""
        try:
            with get_db_session() as db:
                run = db.query(Run).filter(Run.id == run_id).first()
                if run:
                    run.results = results
                    db.commit()
        except Exception as e:
            logger.error(f"Failed to store intermediate results for {run_id}: {e}")

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
            job_ids: Dictionary of task key (pysr_1, pysr_2, ...) to job ID
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
    ) -> bool:
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
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to update run status for {run_id}: {e}")
            return False


class _SlurmSearchLauncher:
    """Runs a discovery session's PySR searches as keyed Slurm tasks."""

    def __init__(
        self,
        orchestrator: AnalysisOrchestrator,
        context: AnalysisContext,
        progress: ProgressTracker,
    ):
        self.orchestrator = orchestrator
        self.context = context
        self.progress = progress
        self.job_ids: dict[str, str] = {}

    async def submit(
        self,
        search_id: str,
        input_data: dict[str, Any],
        on_job_id=None,
    ) -> str:
        compute_settings = get_compute_settings()
        task_input = TaskInput(
            task_type="pysr",
            task_key=search_id,
            run_id=self.context.run_id,
            input_data=input_data,
            callback_url=compute_settings.worker_callback_url,
            callback_token=compute_settings.worker_callback_token,
        )
        job = await self.orchestrator._submit_with_retry(
            task_input, search_id, self.context.run_id, self.progress
        )
        self.job_ids[search_id] = job.job_id
        if on_job_id is not None:
            on_job_id(job.job_id)  # before any await: a cancel from now on reaches the job
        # Stored so that user cancellation (run_service) also cancels these jobs
        await asyncio.to_thread(
            self.orchestrator._store_slurm_job_ids, self.context.run_id, dict(self.job_ids)
        )
        logger.info(f"{search_id} submitted as job {job.job_id}")
        return job.job_id

    async def wait(self, job_id: str) -> tuple[bool, dict[str, Any] | None, str | None]:
        status = await self.orchestrator._wait_for_job(job_id, "PySR", self.context.run_id)
        result = None
        try:
            result = await self.orchestrator.backend.get_task_result(job_id)
        except SlurmBackendError as e:
            if status.state == JobState.COMPLETED:
                return False, None, f"results missing: {e}"
        if status.state == JobState.CANCELLED:
            return False, None, "cancelled"
        if result and result.get("status") == "error":
            return False, None, result.get("error") or "worker reported an error"
        if status.state != JobState.COMPLETED:
            reason = status.error or f"job ended in state {status.state.value}"
            tail = self._stderr_tail(job_id)
            return False, None, f"{reason}: {tail}" if tail else reason
        return True, result, None

    def _stderr_tail(self, job_id: str, n_bytes: int = 1500) -> str:
        """Last lines of the job's stderr, when the staging directory is readable here."""
        path = (getattr(self.orchestrator.backend, "_tasks", {}).get(job_id) or {}).get(
            "stderr_path"
        )
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - n_bytes))
                return f.read().decode("utf-8", errors="replace").strip().splitlines()[-1][:500]
        except (OSError, IndexError):
            return ""

    async def cancel(self, job_id: str) -> None:
        await self.orchestrator.backend.cancel_task(job_id)


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
