"""
PySR symbolic regression task.

Defines the PySR task for discovering mathematical equations.
"""

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.workers.tasks.base import ComputeTask, TaskInput, TaskOutput, TaskType


@dataclass
class PySRConfig:
    """Configuration for PySR symbolic regression."""

    niterations: int = 40
    populations: int = 15
    population_size: int = 33
    ncycles_per_iteration: int = 550
    binary_operators: list[str] = field(default_factory=lambda: ["+", "-", "*", "/"])
    unary_operators: list[str] = field(default_factory=lambda: ["exp", "log", "sqrt", "abs"])
    maxsize: int = 20
    maxdepth: int = 10
    timeout_in_seconds: int = 3600
    parsimony: float = 0.0032
    turbo: bool = True


@dataclass
class PySRInput(TaskInput):
    """Input for PySR task."""

    data: pd.DataFrame
    target_column: str
    predictor_columns: list[str]
    config: PySRConfig = field(default_factory=PySRConfig)


@dataclass
class Equation:
    """A discovered symbolic equation."""

    equation: str
    complexity: int
    loss: float
    score: float
    sympy_format: str | None = None


@dataclass
class ScatterData:
    """Scatter plot data for equation visualization."""

    measured: list[float]
    predicted: list[float]


@dataclass
class PySROutput(TaskOutput):
    """Output from PySR task."""

    equations: list[Equation]
    best_equation: Equation | None = None
    computation_time_seconds: float | None = None
    iterations_completed: int | None = None
    scatter_data: dict[str, ScatterData] | None = None  # equation string -> scatter data


class PySRTask(ComputeTask[PySRInput, PySROutput]):
    """
    PySR symbolic regression task.

    Uses PySR to discover mathematical equations that describe
    the relationship between predictors and target.
    """

    @property
    def task_type(self) -> TaskType:
        return TaskType.PYSR

    def validate_input(self, input_data: PySRInput) -> None:
        """Validate PySR input data."""
        if input_data.data.empty:
            raise ValueError("Input DataFrame is empty")

        if input_data.target_column not in input_data.data.columns:
            raise ValueError(f"Target column '{input_data.target_column}' not in DataFrame")

        missing_predictors = set(input_data.predictor_columns) - set(input_data.data.columns)
        if missing_predictors:
            raise ValueError(f"Predictor columns not in DataFrame: {missing_predictors}")

        if not input_data.predictor_columns:
            raise ValueError("No predictor columns specified")

    def serialize_input(self, input_data: PySRInput) -> dict[str, Any]:
        """Serialize PySR input for JSON transport."""
        # Select only relevant columns
        columns_needed = [input_data.target_column, *input_data.predictor_columns]
        df_subset = input_data.data[columns_needed]

        config_dict = {
            "niterations": input_data.config.niterations,
            "populations": input_data.config.populations,
            "population_size": input_data.config.population_size,
            "ncycles_per_iteration": input_data.config.ncycles_per_iteration,
            "binary_operators": input_data.config.binary_operators,
            "unary_operators": input_data.config.unary_operators,
            "maxsize": input_data.config.maxsize,
            "maxdepth": input_data.config.maxdepth,
            "timeout_in_seconds": input_data.config.timeout_in_seconds,
            "parsimony": input_data.config.parsimony,
            "turbo": input_data.config.turbo,
        }

        return {
            "data": self.serialize_dataframe(df_subset),
            "target_column": input_data.target_column,
            "predictor_columns": input_data.predictor_columns,
            "config": config_dict,
        }

    def deserialize_output(self, data: dict[str, Any]) -> PySROutput:
        """Deserialize PySR output from JSON."""
        if data.get("status") == "error":
            raise ValueError(f"PySR task failed: {data.get('error', 'Unknown error')}")

        equations_data = data.get("equations", [])
        equations = [
            Equation(
                equation=eq["equation"],
                complexity=eq["complexity"],
                loss=eq["loss"],
                score=eq.get("score", 0.0),
                sympy_format=eq.get("sympy_format"),
            )
            for eq in equations_data
        ]

        best_eq = None
        if data.get("best_equation"):
            best_data = data["best_equation"]
            best_eq = Equation(
                equation=best_data["equation"],
                complexity=best_data["complexity"],
                loss=best_data["loss"],
                score=best_data.get("score", 0.0),
                sympy_format=best_data.get("sympy_format"),
            )

        # Deserialize scatter data if present
        scatter_data_raw = data.get("scatter_data", {})
        scatter_data = (
            {
                eq_str: ScatterData(
                    measured=sd["measured"],
                    predicted=sd["predicted"],
                )
                for eq_str, sd in scatter_data_raw.items()
            }
            if scatter_data_raw
            else None
        )

        return PySROutput(
            equations=equations,
            best_equation=best_eq,
            computation_time_seconds=data.get("computation_time_seconds"),
            iterations_completed=data.get("iterations_completed"),
            scatter_data=scatter_data,
        )

    @staticmethod
    def execute(input_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Execute PySR symbolic regression.

        This static method can be called directly in local backend
        or by the worker script on Slurm. Matches syxplain_lib.py approach.

        Args:
            input_dict: Deserialized input dictionary

        Returns:
            Output dictionary ready for serialization
        """
        import logging
        import os
        import tempfile
        import time

        import numpy as np
        import pandas as pd
        from pysr import PySRRegressor

        logger = logging.getLogger(__name__)
        start_time = time.time()

        # Reconstruct DataFrame
        df = pd.DataFrame(**input_dict["data"])
        target_column = input_dict["target_column"]
        predictor_columns = input_dict["predictor_columns"]
        config = input_dict.get("config", {})
        run_id = input_dict.get("run_id", "unknown")

        logger.info(f"PySR: Processing {len(df)} rows, {len(predictor_columns)} predictors")

        X = df[predictor_columns]
        y = df[target_column]

        # Dynamic niterations estimation (from syxplain_lib.py)
        def estimate_niterations():
            sample_nbr, feature_dim_nbr = X.shape
            x_complexity_factor = feature_dim_nbr * np.log10(sample_nbr)

            if np.mean(y) == 0 or len(y) == 0:
                y_complexity_factor = 1
            else:
                noise_level = np.std(y - np.mean(y)) / np.mean(np.abs(y))
                y_complexity_factor = np.clip(1 + noise_level, 1, 3)

            return max(200, int(10 * x_complexity_factor * y_complexity_factor))

        niterations = config.get("niterations") or estimate_niterations()

        # Build constraints (from syxplain_lib.py)
        binary_operators = config.get("binary_operators", ["+", "-", "*", "/"])
        unary_operators = config.get("unary_operators", ["exp", "log", "sqrt", "abs"])

        constraints = {}
        nested_constraints = {}

        if "^" in binary_operators:
            constraints["^"] = (-1, 1)
        if "exp" in unary_operators:
            nested_constraints["exp"] = {"exp": 2}
        if "sin" in unary_operators:
            nested_constraints["sin"] = {"sin": 0}

        # Resource configuration
        cpu_count = os.cpu_count() or 4

        # Isolate temp files for parallel execution
        temp_dir = os.path.join(tempfile.gettempdir(), f"pysr_{run_id}")
        os.makedirs(temp_dir, exist_ok=True)

        logger.info(f"PySR config: niterations={niterations}, cpus={cpu_count}")

        # Create PySR model with config
        model = PySRRegressor(
            niterations=niterations,
            populations=config.get("populations", 15),
            population_size=config.get("population_size", 33),
            ncycles_per_iteration=config.get("ncycles_per_iteration", 550),
            binary_operators=binary_operators,
            unary_operators=unary_operators,
            maxsize=config.get("maxsize", 20),
            maxdepth=config.get("maxdepth", 10),
            timeout_in_seconds=config.get("timeout_in_seconds", 3600),
            parsimony=config.get("parsimony", 0.0032),
            turbo=config.get("turbo", True),
            constraints=constraints,
            nested_constraints=nested_constraints,
            extra_sympy_mappings={},
            parallelism="multiprocessing",
            procs=cpu_count,
            verbosity=1,
            progress=True,
            tempdir=temp_dir,
            feature_names=predictor_columns,
        )

        # Run symbolic regression
        model.fit(X, y)

        # Extract equations from results
        equations_list = []
        scatter_data = {}

        if hasattr(model, "equations_") and model.equations_ is not None:
            equations_df = model.equations_

            # Select equations with loss < best_loss * 1.5 (matching legacy behavior)
            best_loss = float(equations_df["loss"].min())
            selected_equations = equations_df[equations_df["loss"] < best_loss * 1.5].copy()

            # Subsample data for scatter plots (max 500 points for frontend performance)
            max_scatter_points = 500
            if len(y) > max_scatter_points:
                rng = np.random.default_rng(42)
                indices = rng.choice(len(y), max_scatter_points, replace=False)
                indices = np.sort(indices)
                X_sample = X.iloc[indices]
                y_actual_sample = y.iloc[indices].values
            else:
                X_sample = X
                y_actual_sample = y.values

            X_sample_np = X_sample.values

            # Generate scatter data for selected equations
            for idx, row in selected_equations.iterrows():
                eq_string = str(row.get("equation", ""))
                equations_list.append(
                    {
                        "equation": eq_string,
                        "complexity": int(row.get("complexity", 0)),
                        "loss": float(row.get("loss", float("inf"))),
                        "score": float(row.get("score", 0.0)),
                        "sympy_format": str(row.get("sympy_format", "")),
                    }
                )

                # Generate predictions using lambda_format
                try:
                    if "lambda_format" in row and row["lambda_format"] is not None:
                        lambda_fn = row["lambda_format"]
                        y_pred = lambda_fn(X_sample_np)
                    else:
                        # Fallback to model.predict with index
                        y_pred = model.predict(X_sample, index=idx)

                    if hasattr(y_pred, "values"):
                        y_pred = y_pred.values

                    scatter_data[eq_string] = {
                        "measured": y_actual_sample.tolist(),
                        "predicted": y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred),
                    }
                except Exception as e:
                    logger.warning(
                        f"Failed to generate scatter data for equation '{eq_string[:50]}...': {e}"
                    )

            logger.info(f"Generated scatter data for {len(scatter_data)} equations")

        # Find best equation (lowest loss)
        best_equation = None
        if equations_list:
            sorted_eqs = sorted(equations_list, key=lambda e: e["loss"])
            best_equation = sorted_eqs[0] if sorted_eqs else None

        elapsed = time.time() - start_time
        logger.info(f"PySR completed: {len(equations_list)} equations in {elapsed:.1f}s")

        return {
            "status": "success",
            "equations": equations_list,
            "best_equation": best_equation,
            "computation_time_seconds": elapsed,
            "iterations_completed": niterations,
            "scatter_data": scatter_data,
        }
