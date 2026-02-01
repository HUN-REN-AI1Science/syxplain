"""
SHAP interaction analysis task.

Defines the SHAP task for computing feature interactions using SHAP values.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backend.workers.tasks.base import ComputeTask, TaskInput, TaskOutput, TaskType


@dataclass
class SHAPInput(TaskInput):
    """Input for SHAP analysis task."""

    data: pd.DataFrame
    target_column: str
    predictor_columns: list[str]
    subsample_fraction: float = 0.1
    subsample_min: int = 1000
    subsample_max: int = 5000


@dataclass
class SHAPInteraction:
    """A single feature interaction result."""

    feature1: str
    feature2: str
    interaction_strength: float
    rank: int


@dataclass
class Visualization:
    """A visualization result."""

    filename: str
    content_b64: str
    type: str  # "feature_plot" or "interaction_plot"


@dataclass
class SHAPOutput(TaskOutput):
    """Output from SHAP analysis task."""

    interactions: list[SHAPInteraction]
    top_features: list[str]
    computation_time_seconds: float | None = None
    samples_used: int | None = None
    visualizations: list[Visualization] | None = None


class SHAPTask(ComputeTask[SHAPInput, SHAPOutput]):
    """
    SHAP interaction analysis task.

    Computes feature interactions using SHAP values to identify
    which features interact strongly when predicting the target.
    """

    @property
    def task_type(self) -> TaskType:
        return TaskType.SHAP

    def validate_input(self, input_data: SHAPInput) -> None:
        """Validate SHAP input data."""
        if input_data.data.empty:
            raise ValueError("Input DataFrame is empty")

        if input_data.target_column not in input_data.data.columns:
            raise ValueError(f"Target column '{input_data.target_column}' not in DataFrame")

        missing_predictors = set(input_data.predictor_columns) - set(input_data.data.columns)
        if missing_predictors:
            raise ValueError(f"Predictor columns not in DataFrame: {missing_predictors}")

        if not input_data.predictor_columns:
            raise ValueError("No predictor columns specified")

        if input_data.subsample_fraction <= 0 or input_data.subsample_fraction > 1:
            raise ValueError("subsample_fraction must be between 0 and 1")

    def serialize_input(self, input_data: SHAPInput) -> dict[str, Any]:
        """Serialize SHAP input for JSON transport."""
        # Select only relevant columns for efficiency
        columns_needed = [input_data.target_column, *input_data.predictor_columns]
        df_subset = input_data.data[columns_needed]

        return {
            "data": self.serialize_dataframe(df_subset),
            "target_column": input_data.target_column,
            "predictor_columns": input_data.predictor_columns,
            "subsample_fraction": input_data.subsample_fraction,
            "subsample_min": input_data.subsample_min,
            "subsample_max": input_data.subsample_max,
        }

    def deserialize_output(self, data: dict[str, Any]) -> SHAPOutput:
        """Deserialize SHAP output from JSON."""
        if data.get("status") == "error":
            raise ValueError(f"SHAP task failed: {data.get('error', 'Unknown error')}")

        interactions_data = data.get("interactions", [])
        interactions = [
            SHAPInteraction(
                feature1=i["feature1"],
                feature2=i["feature2"],
                interaction_strength=i["interaction_strength"],
                rank=i.get("rank", idx + 1),
            )
            for idx, i in enumerate(interactions_data)
        ]

        visualizations_data = data.get("visualizations", [])
        visualizations = (
            [
                Visualization(
                    filename=v["filename"],
                    content_b64=v["content_b64"],
                    type=v["type"],
                )
                for v in visualizations_data
            ]
            if visualizations_data
            else None
        )

        return SHAPOutput(
            interactions=interactions,
            top_features=data.get("top_features", []),
            computation_time_seconds=data.get("computation_time_seconds"),
            samples_used=data.get("samples_used"),
            visualizations=visualizations,
        )

    @staticmethod
    def _generate_visualizations(
        df: "pd.DataFrame",
        target_column: str,
        predictor_columns: list[str],
        top_interactions: list[dict[str, Any]],
        max_interaction_plots: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Generate visualization plots for SHAP analysis results.

        Creates:
        - Feature vs target scatter plots (one per predictor)
        - Interaction pair plots (for top SHAP interactions)

        Args:
            df: Input DataFrame
            target_column: Name of target column
            predictor_columns: List of predictor column names
            top_interactions: List of top interaction pairs from SHAP analysis
            max_interaction_plots: Maximum number of interaction plots to generate

        Returns:
            List of visualization dictionaries with filename, content_b64, and type
        """
        import base64
        import io
        import logging

        import matplotlib

        matplotlib.use("Agg")  # Non-interactive backend for headless execution
        import matplotlib.pyplot as plt

        logger = logging.getLogger(__name__)
        visualizations = []

        # Feature vs target plots
        logger.info(f"Generating {len(predictor_columns)} feature vs target plots")
        for col in predictor_columns:
            try:
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.scatter(df[col], df[target_column], alpha=0.1)
                ax.set_xlabel(col)
                ax.set_ylabel(target_column)
                ax.set_title(f"{col} vs {target_column}")
                plt.tight_layout()

                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=100)
                buf.seek(0)
                visualizations.append(
                    {
                        "filename": f"{col}_vs_{target_column}.png",
                        "content_b64": base64.b64encode(buf.getvalue()).decode(),
                        "type": "feature_plot",
                    }
                )
                plt.close(fig)
            except Exception as e:
                logger.warning(f"Failed to generate plot for {col}: {e}")

        # Interaction plots (for top interactions)
        interactions_to_plot = top_interactions[:max_interaction_plots]
        logger.info(f"Generating {len(interactions_to_plot)} interaction plots")
        for interaction in interactions_to_plot:
            f1 = interaction["feature1"]
            f2 = interaction["feature2"]
            try:
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.scatter(df[f1], df[f2], alpha=0.1)
                ax.set_xlabel(f1)
                ax.set_ylabel(f2)
                ax.set_title(f"{f1} vs {f2}")
                plt.tight_layout()

                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=100)
                buf.seek(0)
                visualizations.append(
                    {
                        "filename": f"{f1}_vs_{f2}_interaction.png",
                        "content_b64": base64.b64encode(buf.getvalue()).decode(),
                        "type": "interaction_plot",
                    }
                )
                plt.close(fig)
            except Exception as e:
                logger.warning(f"Failed to generate interaction plot for {f1} vs {f2}: {e}")

        logger.info(f"Generated {len(visualizations)} total visualizations")
        return visualizations

    @staticmethod
    def execute(input_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Execute SHAP analysis using actual SHAP interaction values.

        This static method can be called directly in local backend
        or by the worker script on Slurm.

        Args:
            input_dict: Deserialized input dictionary

        Returns:
            Output dictionary ready for serialization
        """
        import logging
        import time

        import numpy as np
        import pandas as pd
        import shap
        from sklearn.ensemble import RandomForestRegressor

        logger = logging.getLogger(__name__)
        start_time = time.time()

        # Reconstruct DataFrame
        df = pd.DataFrame(**input_dict["data"])
        target_column = input_dict["target_column"]
        predictor_columns = input_dict["predictor_columns"]
        subsample_fraction = input_dict.get("subsample_fraction", 0.1)
        subsample_min = input_dict.get("subsample_min", 1000)
        subsample_max = input_dict.get("subsample_max", 5000)
        percent_of_total_mass = input_dict.get("percent_of_total_mass", 80)
        generate_viz = input_dict.get("generate_visualizations", True)

        n_features = len(predictor_columns)

        # Subsample for SHAP computation
        n_samples = len(df)
        target_samples = int(n_samples * subsample_fraction)
        target_samples = max(subsample_min, min(subsample_max, target_samples))
        target_samples = min(target_samples, n_samples)

        if target_samples < n_samples:
            rng = np.random.default_rng(845506771)
            indices = rng.choice(n_samples, size=target_samples, replace=False)
            df_subsampled = df.iloc[indices].reset_index(drop=True)
        else:
            df_subsampled = df

        logger.info(f"SHAP: Using {len(df_subsampled)} samples for computation")

        X = df[predictor_columns]
        X_subsampled = df_subsampled[predictor_columns]
        y = df[target_column]

        # Train RandomForest model
        logger.info("Training RandomForest model...")
        model = RandomForestRegressor(n_estimators=200, n_jobs=-1)
        model.fit(X, y)

        # Compute SHAP interaction values
        logger.info("Computing SHAP interaction values...")
        explainer = shap.TreeExplainer(model)
        shap_interaction_values = explainer.shap_interaction_values(X_subsampled)

        # Validate shape - should be 3D (samples, features, features)
        if not isinstance(shap_interaction_values, np.ndarray) or shap_interaction_values.ndim != 3:
            raise ValueError(
                f"Expected 3D array for interaction values, got shape: {shap_interaction_values.shape}"
            )

        # Calculate mean absolute interaction matrix
        mean_abs_interaction_matrix = np.mean(np.abs(shap_interaction_values), axis=0)

        # Create list of unique interaction pairs with values
        interaction_pairs_with_values = []
        for i in range(n_features):
            for j in range(i + 1, n_features):
                # Average (i,j) and (j,i) elements
                interaction_value = (
                    mean_abs_interaction_matrix[i, j] + mean_abs_interaction_matrix[j, i]
                ) / 2
                interaction_pairs_with_values.append(
                    {
                        "feature1": predictor_columns[i],
                        "feature2": predictor_columns[j],
                        "interaction_strength": float(interaction_value),
                    }
                )

        # Sort by magnitude
        interaction_pairs_with_values.sort(key=lambda x: x["interaction_strength"], reverse=True)

        # Calculate total mass and select top interactions
        total_mass = sum(x["interaction_strength"] for x in interaction_pairs_with_values)
        target_mass = total_mass * (percent_of_total_mass / 100)

        top_interactions = []
        accumulated_mass = 0
        for idx, pair in enumerate(interaction_pairs_with_values):
            pair["rank"] = idx + 1
            if accumulated_mass < target_mass:
                top_interactions.append(pair)
                accumulated_mass += pair["interaction_strength"]

        # Extract top features from interactions
        feature_set = set()
        for pair in top_interactions:
            feature_set.add(pair["feature1"])
            feature_set.add(pair["feature2"])
        top_features = list(feature_set)[:10]

        # Generate visualizations
        visualizations = []
        if generate_viz:
            visualizations = SHAPTask._generate_visualizations(
                df=df,
                target_column=target_column,
                predictor_columns=predictor_columns,
                top_interactions=top_interactions,
            )

        elapsed = time.time() - start_time
        logger.info(
            f"SHAP completed: {len(top_interactions)} interactions covering "
            f"{accumulated_mass / total_mass * 100:.1f}% of total mass"
        )

        return {
            "status": "success",
            "interactions": top_interactions,
            "top_features": top_features,
            "computation_time_seconds": elapsed,
            "samples_used": len(df_subsampled),
            "total_interaction_mass": float(total_mass),
            "covered_mass_percent": float(accumulated_mass / total_mass * 100)
            if total_mass > 0
            else 0,
            "visualizations": visualizations,
        }
