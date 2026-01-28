"""
Analysis orchestrator service.

Coordinates the workflow between compute backends and LLM operations,
managing the complete analysis pipeline from data ingestion to explanation.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.core.config import get_settings, get_compute_settings
from backend.infrastructure.compute import (
    ComputeBackend,
    ComputeTaskInput,
    TaskState,
    get_compute_backend,
)
from backend.infrastructure.database.connection import get_db_session
from backend.infrastructure.database.models import Run, RunArtifact
from backend.services.progress_service import ProgressTracker
from backend.workers.tasks import SHAPTask, PySRTask

logger = logging.getLogger(__name__)


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
    problem_description: Dict[str, Any]
    data: pd.DataFrame
    target_column: str
    predictor_columns: List[str]
    analysis_type: str = "quick"
    deep_research_model: Optional[str] = None
    progress: Optional[ProgressTracker] = None
    # User-provided API keys (not stored, only in memory)
    user_api_key: Optional[str] = None
    user_model: Optional[str] = None


class AnalysisOrchestrator:
    """
    Orchestrates the complete analysis workflow.

    Handles the coordination between:
    1. Compute-intensive tasks (SHAP, PySR) on backends (local/Slurm)
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
        backend: Optional[ComputeBackend] = None,
        config: Optional[OrchestratorConfig] = None,
    ):
        """
        Initialize orchestrator.

        Args:
            backend: Compute backend to use (defaults to configured backend)
            config: Orchestrator configuration
        """
        self._backend = backend
        self._config = config or OrchestratorConfig()

    @property
    def backend(self) -> ComputeBackend:
        """Get compute backend (lazy initialization)."""
        if self._backend is None:
            self._backend = get_compute_backend()
        return self._backend

    async def run_analysis(self, context: AnalysisContext) -> Dict[str, Any]:
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
            self._update_run_status(run_id, "running")
            progress.update_progress("initialization", status="Initializing analysis")

            # Step 1: Data summary
            progress.update_progress("data_summary", status="Analyzing dataset")
            data_summary = self._generate_data_summary(context)

            # Step 1.5: Generate feature visualizations for LLM
            progress.update_progress("visualization", status="Generating feature visualizations")
            feature_visualizations = self._generate_feature_visualizations(context)

            # Step 2: Generate PySR config using LLM
            progress.update_progress(
                "pysr_config_generation",
                status="Generating symbolic regression configuration"
            )
            pysr_config = await self._generate_pysr_config(
                context, data_summary, visualizations_b64=feature_visualizations
            )

            # Step 3: Submit compute tasks
            progress.update_progress(
                "compute_submission",
                status="Submitting compute tasks"
            )
            compute_results = await self._run_compute_tasks(context, pysr_config, progress)

            # Step 4: LLM explanation of results
            progress.update_progress(
                "llm_explanation",
                status="Generating explanations"
            )
            explanations = await self._generate_explanations(
                context, compute_results, data_summary
            )

            # Step 5: Optional deep research
            if context.analysis_type == "deep" and context.deep_research_model:
                progress.update_progress(
                    "deep_research",
                    status="Performing deep research"
                )
                explanations = await self._run_deep_research(
                    context, compute_results, explanations
                )

            # Step 6: Finalize and store results
            progress.update_progress("finalization", status="Finalizing results")
            final_results = self._compile_final_results(
                context, compute_results, explanations
            )

            # Save artifacts (including visualizations from compute results)
            visualizations = compute_results.get("visualizations", [])
            self._save_artifacts(run_id, final_results, progress, visualizations=visualizations)

            # Mark as completed
            self._update_run_status(run_id, "completed", results=final_results)
            progress.set_progress(100, "Analysis complete")

            logger.info(f"Analysis completed successfully for run {run_id}")
            return final_results

        except Exception as e:
            logger.error(f"Analysis failed for run {run_id}: {e}", exc_info=True)
            self._update_run_status(run_id, "failed", error=str(e))
            raise OrchestratorError(f"Analysis failed: {e}") from e

    def _generate_data_summary(self, context: AnalysisContext) -> Dict[str, Any]:
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
    ) -> List[str]:
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
        data_summary: Dict[str, Any],
        visualizations_b64: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
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
            # Generate data summary CSV for LLM
            summary_csv = pd.DataFrame(data_summary.get("target_stats", {}), index=[0]).to_csv()

            config_json = generate_pysr_config(
                project_description=json.dumps(context.problem_description),
                dataset_statistics=summary_csv,
                visualizations_b64=visualizations_b64 or [],
                user_api_key=context.user_api_key,
                user_model=context.user_model,
            )
            return json.loads(config_json)
        except Exception as e:
            logger.warning(f"LLM config generation failed, using defaults: {e}")
            # Return default config
            return {
                "niterations": 40,
                "populations": 15,
                "binary_operators": ["+", "-", "*", "/"],
                "unary_operators": ["exp", "log", "sqrt", "abs"],
                "maxsize": 20,
            }

    async def _run_compute_tasks(
        self,
        context: AnalysisContext,
        pysr_config: Dict[str, Any],
        progress: ProgressTracker,
    ) -> Dict[str, Any]:
        """
        Submit and monitor compute tasks on the backend.

        Runs SHAP and PySR tasks, possibly in parallel depending
        on available resources.
        """
        compute_settings = get_compute_settings()
        results = {}

        # Build task inputs
        shap_task_input = ComputeTaskInput(
            task_type="shap",
            run_id=context.run_id,
            input_data={
                "data": context.data[
                    [context.target_column] + context.predictor_columns
                ].to_dict(orient="split"),
                "target_column": context.target_column,
                "predictor_columns": context.predictor_columns,
                "generate_visualizations": True,
            },
            callback_url=compute_settings.worker_callback_url,
            callback_token=compute_settings.worker_callback_token,
        )

        pysr_task_input = ComputeTaskInput(
            task_type="pysr",
            run_id=context.run_id,
            input_data={
                "data": context.data[
                    [context.target_column] + context.predictor_columns
                ].to_dict(orient="split"),
                "target_column": context.target_column,
                "predictor_columns": context.predictor_columns,
                "config": pysr_config,
            },
            callback_url=compute_settings.worker_callback_url,
            callback_token=compute_settings.worker_callback_token,
        )

        # Submit tasks
        progress.update_progress("shap_submission", status="Running SHAP analysis")
        shap_job = await self.backend.submit_task(shap_task_input)
        logger.info(f"SHAP task submitted as job {shap_job.job_id}")

        progress.update_progress("pysr_submission", status="Running symbolic regression")
        pysr_job = await self.backend.submit_task(pysr_task_input)
        logger.info(f"PySR task submitted as job {pysr_job.job_id}")

        # Store job IDs in database for cancellation
        self._store_slurm_job_ids(context.run_id, {
            "shap_job_id": shap_job.job_id,
            "pysr_job_id": pysr_job.job_id,
        })

        # Wait for completion (can run in parallel on cluster)
        progress.update_progress("compute_waiting", status="Waiting for compute tasks")

        shap_status = await self.backend.wait_for_completion(
            shap_job.job_id,
            poll_interval=self._config.poll_interval,
            timeout=self._config.compute_timeout,
        )

        pysr_status = await self.backend.wait_for_completion(
            pysr_job.job_id,
            poll_interval=self._config.poll_interval,
            timeout=self._config.compute_timeout,
        )

        # Check for failures
        if shap_status.state != TaskState.COMPLETED:
            raise OrchestratorError(f"SHAP task failed: {shap_status.error}")

        if pysr_status.state != TaskState.COMPLETED:
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
        compute_results: Dict[str, Any],
        data_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
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

            explanations = generate_equation_explanation(
                project_spec_json=json.dumps(context.problem_description),
                data_spec_json=json.dumps(data_spec),
                deep_research_context=None,
                user_api_key=context.user_api_key,
                user_model=context.user_model,
            )
            return explanations
        except Exception as e:
            logger.error(f"Explanation generation failed: {e}")
            return {"error": str(e), "equations": compute_results.get("pysr", {}).get("equations", [])}

    async def _run_deep_research(
        self,
        context: AnalysisContext,
        compute_results: Dict[str, Any],
        explanations: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Run deep research using o4-mini.

        This runs on the main backend (has LLM keys).
        """
        from backend.services.llm_service import deep_research_equations, generate_equation_explanation

        try:
            # Get features from problem description
            features_dict = context.problem_description.get("features", {})

            if not features_dict:
                logger.warning("No features defined for deep research")
                return explanations

            # Run deep research to find scientific equations
            deep_result = deep_research_equations(
                features_dict=features_dict,
                model_name=context.deep_research_model,
                user_api_key=context.user_api_key,
            )

            # Re-generate explanations with deep research context
            equations = compute_results.get("pysr", {}).get("equations", [])
            data_spec = {
                "equation": [eq.get("equation", "") for eq in equations],
                "loss": [eq.get("loss", 0) for eq in equations],
                "complexity": [eq.get("complexity", 0) for eq in equations],
            }

            enhanced_explanations = generate_equation_explanation(
                project_spec_json=json.dumps(context.problem_description),
                data_spec_json=json.dumps(data_spec),
                deep_research_context=deep_result,
                user_api_key=context.user_api_key,
                user_model=context.user_model,
            )

            return enhanced_explanations
        except Exception as e:
            logger.error(f"Deep research failed: {e}")
            return explanations

    def _compile_final_results(
        self,
        context: AnalysisContext,
        compute_results: Dict[str, Any],
        explanations: Dict[str, Any],
    ) -> Dict[str, Any]:
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
        results: Dict[str, Any],
        progress: ProgressTracker,
        visualizations: Optional[List[Dict[str, Any]]] = None,
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
                "pysr_explanations.json",
                results_json,
                media_type="application/json"
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
                        progress.save_artifact(
                            filename,
                            content_bytes,
                            media_type="image/png"
                        )
                except Exception as e:
                    logger.warning(f"Failed to save visualization {viz.get('filename')}: {e}")

            logger.info(f"Saved {len(visualizations)} visualizations for run {run_id}")

    def _store_slurm_job_ids(self, run_id: str, job_ids: Dict[str, str]) -> None:
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
        results: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update run status in database."""
        try:
            with get_db_session() as db:
                run = db.query(Run).filter(Run.id == run_id).first()
                if run:
                    run.status = status
                    # Set start_time when transitioning to running
                    if status == "running" and run.start_time is None:
                        run.start_time = datetime.utcnow()
                    # Set finish_time for terminal states
                    if status in ("completed", "failed", "timeout", "cancelled"):
                        run.finish_time = datetime.utcnow()
                    if results:
                        run.results = results
                    if error:
                        run.error = error
                    if status == "completed":
                        run.progress = 100
                    db.commit()
        except Exception as e:
            logger.error(f"Failed to update run status for {run_id}: {e}")


class OrchestratorError(Exception):
    """Error during orchestration."""
    pass


async def run_orchestrated_analysis(
    run_id: str,
    problem_desc: Dict[str, Any],
    data: pd.DataFrame,
    user_id: str,
    analysis_type: str = "quick",
    deep_research_model: Optional[str] = None,
    user_api_key: Optional[str] = None,
    user_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to run analysis with orchestrator.

    Args:
        run_id: UUID of the run
        problem_desc: Problem description dictionary
        data: Input DataFrame
        user_id: Owner user ID
        analysis_type: 'quick' or 'deep'
        deep_research_model: Model for deep analysis
        user_api_key: Optional user-provided API key
        user_model: Optional user-specified model

    Returns:
        Analysis results
    """
    target_column = problem_desc["target_variable"]
    predictor_columns = list(problem_desc["features"].keys())

    # Filter to numeric predictors
    numeric_predictors = [
        col for col in predictor_columns
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
    )

    orchestrator = AnalysisOrchestrator()
    return await orchestrator.run_analysis(context)
