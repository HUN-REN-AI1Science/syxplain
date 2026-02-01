"""
SHAP interaction analysis task.

Computes SHAP interaction values to identify important feature pairs.
"""

from typing import Any

import numpy as np

from slurm_worker.config import SHAPConfig
from slurm_worker.logging_config import get_logger
from slurm_worker.tasks.base import DataFrameInput, Task, TaskResult
from slurm_worker.tasks.registry import TaskRegistry
from slurm_worker.visualization.generators import VisualizationService

logger = get_logger("tasks.shap")


class SHAPAnalyzer:
    """
    Handles SHAP interaction value computation.

    Separates the SHAP analysis logic from the task orchestration,
    following the Single Responsibility Principle.
    """

    def __init__(self, config: SHAPConfig):
        """
        Initialize analyzer with configuration.

        Args:
            config: SHAP configuration
        """
        self.config = config

    def subsample(self, df: Any, n_samples: int) -> tuple[Any, np.ndarray]:
        """
        Subsample DataFrame for SHAP computation.

        Args:
            df: Input DataFrame
            n_samples: Total samples in DataFrame

        Returns:
            Tuple of (subsampled_df, indices)
        """
        target_samples = int(n_samples * self.config.subsample_fraction)
        target_samples = max(self.config.subsample_min, target_samples)
        target_samples = min(self.config.subsample_max, target_samples)
        target_samples = min(target_samples, n_samples)

        if target_samples < n_samples:
            rng = np.random.default_rng(self.config.random_seed)
            indices = rng.choice(n_samples, size=target_samples, replace=False)
            return df.iloc[indices].reset_index(drop=True), indices
        return df, np.arange(n_samples)

    def train_model(self, X: Any, y: Any) -> Any:
        """
        Train RandomForest model for SHAP analysis.

        Args:
            X: Feature matrix
            y: Target vector

        Returns:
            Trained model
        """
        from sklearn.ensemble import RandomForestRegressor

        model = RandomForestRegressor(
            n_estimators=self.config.n_estimators,
            n_jobs=-1,
        )
        model.fit(X, y)
        return model

    def compute_interactions(
        self,
        model: Any,
        X_subsampled: Any,
        predictor_columns: list[str],
    ) -> tuple[list[dict[str, Any]], float]:
        """
        Compute SHAP interaction values and extract top interactions.

        Args:
            model: Trained model
            X_subsampled: Subsampled feature matrix
            predictor_columns: Feature names

        Returns:
            Tuple of (interaction_pairs, total_mass)
        """
        import shap

        explainer = shap.TreeExplainer(model)
        shap_interaction_values = explainer.shap_interaction_values(X_subsampled)

        if not isinstance(shap_interaction_values, np.ndarray) or shap_interaction_values.ndim != 3:
            raise ValueError(f"Expected 3D array, got shape: {shap_interaction_values.shape}")

        mean_abs_matrix = np.mean(np.abs(shap_interaction_values), axis=0)
        n_features = len(predictor_columns)

        interaction_pairs = []
        for i in range(n_features):
            for j in range(i + 1, n_features):
                value = (mean_abs_matrix[i, j] + mean_abs_matrix[j, i]) / 2
                interaction_pairs.append(
                    {
                        "feature1": predictor_columns[i],
                        "feature2": predictor_columns[j],
                        "interaction_strength": float(value),
                    }
                )

        interaction_pairs.sort(key=lambda x: x["interaction_strength"], reverse=True)
        total_mass = sum(x["interaction_strength"] for x in interaction_pairs)

        return interaction_pairs, total_mass

    def select_top_interactions(
        self,
        interaction_pairs: list[dict[str, Any]],
        total_mass: float,
    ) -> tuple[list[dict[str, Any]], float]:
        """
        Select top interactions covering target percentage of total mass.

        Args:
            interaction_pairs: All interaction pairs sorted by strength
            total_mass: Total interaction mass

        Returns:
            Tuple of (top_interactions, accumulated_mass)
        """
        target_mass = total_mass * (self.config.percent_of_total_mass / 100)

        top_interactions = []
        accumulated_mass = 0.0

        for idx, pair in enumerate(interaction_pairs):
            pair["rank"] = idx + 1
            if accumulated_mass < target_mass:
                top_interactions.append(pair)
                accumulated_mass += pair["interaction_strength"]

        return top_interactions, accumulated_mass

    def extract_top_features(
        self,
        top_interactions: list[dict[str, Any]],
        max_features: int = 10,
    ) -> list[str]:
        """
        Extract unique features from top interactions.

        Args:
            top_interactions: Top interaction pairs
            max_features: Maximum features to return

        Returns:
            List of feature names
        """
        feature_set = set()
        for pair in top_interactions:
            feature_set.add(pair["feature1"])
            feature_set.add(pair["feature2"])
        return list(feature_set)[:max_features]


@TaskRegistry.register("shap")
class SHAPTask(Task):
    """
    SHAP interaction analysis task.

    Computes SHAP interaction values to identify important feature
    pairs for symbolic regression.
    """

    name = "shap"

    def _validate_input(self, input_data: dict[str, Any]) -> None:
        """Validate SHAP task input."""
        required = ["data", "target_column", "predictor_columns"]
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        if not input_data["predictor_columns"]:
            raise ValueError("predictor_columns cannot be empty")

    def _get_config(self, input_data: dict[str, Any]) -> SHAPConfig:
        """Extract SHAP configuration from input data."""
        return SHAPConfig(
            subsample_fraction=input_data.get("subsample_fraction", 0.1),
            subsample_min=input_data.get("subsample_min", 1000),
            subsample_max=input_data.get("subsample_max", 5000),
            percent_of_total_mass=input_data.get("percent_of_total_mass", 80),
            generate_visualizations=input_data.get("generate_visualizations", True),
        )

    def _execute(self, input_data: dict[str, Any]) -> TaskResult:
        """Execute SHAP analysis."""
        self._report(10, "Loading data", "shap_loading")

        # Parse input
        df_input = DataFrameInput.from_dict(input_data)
        config = self._get_config(input_data)
        analyzer = SHAPAnalyzer(config)

        logger.info(f"Loaded data: {df_input.n_rows} rows, {df_input.n_features} predictors")

        # Subsample for SHAP computation
        df_subsampled, _ = analyzer.subsample(df_input.df, df_input.n_rows)
        X_subsampled = df_subsampled[df_input.predictor_columns]
        logger.info(f"Subsampled to {len(df_subsampled)} rows")

        self._report(20, "Training model", "shap_training")
        model = analyzer.train_model(df_input.X, df_input.y)

        self._report(40, "Computing SHAP interaction values", "shap_computing")
        interaction_pairs, total_mass = analyzer.compute_interactions(
            model, X_subsampled, df_input.predictor_columns
        )

        self._report(60, "Analyzing interactions", "shap_interactions")
        top_interactions, accumulated_mass = analyzer.select_top_interactions(
            interaction_pairs, total_mass
        )
        top_features = analyzer.extract_top_features(top_interactions)

        self._report(75, "Generating visualizations", "shap_visualizations")
        visualizations = []
        if config.generate_visualizations:
            viz_service = VisualizationService()
            visualizations = viz_service.generate_all(
                df=df_input.df,
                target_column=df_input.target_column,
                predictor_columns=df_input.predictor_columns,
                interactions=top_interactions,
                max_interaction_plots=config.max_interaction_plots,
            )

        self._report(90, "Finalizing", "shap_finalizing")

        coverage = (accumulated_mass / total_mass * 100) if total_mass > 0 else 0
        logger.info(
            f"SHAP completed: {len(top_interactions)} interactions covering {coverage:.1f}%"
        )

        return TaskResult.success(
            interactions=top_interactions,
            top_features=top_features,
            samples_used=len(df_subsampled),
            total_interaction_mass=float(total_mass),
            covered_mass_percent=float(coverage),
            visualizations=visualizations,
        )
