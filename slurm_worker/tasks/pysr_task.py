"""
PySR symbolic regression task.

Discovers mathematical equations that fit the data using genetic programming.
"""

import inspect
import os
import tempfile
from typing import Any

import numpy as np

from slurm_worker.config import PySRConfig
from slurm_worker.logging_config import get_logger
from slurm_worker.tasks.base import DataFrameInput, Task, TaskResult
from slurm_worker.tasks.registry import TaskRegistry

logger = get_logger("tasks.pysr")

# Target transforms the backend may request; PySR then searches f(X) ~ transform(y).
# The backend wraps the returned equations with the inverse when scoring them.
TARGET_TRANSFORMS = {
    "log": np.log,
    "log1p": np.log1p,
    "sqrt": np.sqrt,
}


def _supports_guesses() -> bool:
    """Warm-start guesses arrived in newer PySR releases; older ones lack the argument."""
    from pysr import PySRRegressor

    return "guesses" in inspect.signature(PySRRegressor.__init__).parameters


class PySRConfigBuilder:
    """
    Builds PySR configuration with dynamic estimation.

    Separates configuration logic from task execution,
    following the Single Responsibility Principle.
    """

    def __init__(self, base_config: PySRConfig):
        """
        Initialize builder with base configuration.

        Args:
            base_config: Base PySR configuration
        """
        self.config = base_config

    def estimate_iterations(self, X: Any, y: Any) -> int:
        """
        Dynamically estimate optimal number of iterations.

        Based on data complexity factors from syxplain_lib.

        Args:
            X: Feature matrix
            y: Target vector

        Returns:
            Estimated number of iterations
        """
        sample_nbr, feature_dim_nbr = X.shape
        x_complexity_factor = feature_dim_nbr * np.log10(sample_nbr)

        y_mean = np.mean(y)
        if y_mean == 0 or len(y) == 0:
            y_complexity_factor = 1
        else:
            noise_level = np.std(y - y_mean) / np.mean(np.abs(y))
            y_complexity_factor = np.clip(1 + noise_level, 1, 3)

        return max(200, int(10 * x_complexity_factor * y_complexity_factor))

    def build_constraints(self) -> tuple[dict, dict]:
        """
        Build operator constraints.

        Returns:
            Tuple of (constraints, nested_constraints)
        """
        constraints = {}
        nested_constraints = {}

        if "^" in self.config.binary_operators:
            constraints["^"] = (-1, 1)
        if "exp" in self.config.unary_operators:
            nested_constraints["exp"] = {"exp": 2}
        if "sin" in self.config.unary_operators:
            nested_constraints["sin"] = {"sin": 0}

        return constraints, nested_constraints

    def get_niterations(self, X: Any, y: Any) -> int:
        """
        Get number of iterations (configured or estimated).

        Args:
            X: Feature matrix
            y: Target vector

        Returns:
            Number of iterations
        """
        if self.config.niterations is not None:
            return self.config.niterations
        return self.estimate_iterations(X, y)


class EquationExtractor:
    """
    Extracts and processes equations from PySR results.

    Handles equation selection and scatter data generation.
    """

    def __init__(self, max_scatter_points: int = 500, seed: int = 42, full_front: bool = False):
        """
        Initialize extractor.

        Args:
            max_scatter_points: Maximum points for scatter plots
            seed: Random seed for subsampling
            full_front: Return the whole hall of fame without scatter data (the backend
                re-scores every equation itself)
        """
        self.max_scatter_points = max_scatter_points
        self.seed = seed
        self.full_front = full_front

    def extract_equations(
        self,
        model: Any,
        X: Any,
        y: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, list[float]]], dict[str, Any] | None]:
        """
        Extract equations and generate scatter data.

        Args:
            model: Fitted PySR model
            X: Feature matrix
            y: Target vector

        Returns:
            Tuple of (equations_list, scatter_data, best_equation)
        """
        equations_list = []
        scatter_data = {}

        if not hasattr(model, "equations_") or model.equations_ is None:
            return equations_list, scatter_data, None

        equations_df = model.equations_

        # Select equations with loss < best_loss * 1.5
        best_loss = float(equations_df["loss"].min())
        if self.full_front:
            selected = equations_df.copy()
        else:
            selected = equations_df[equations_df["loss"] < best_loss * 1.5].copy()

        # Prepare scatter data samples
        X_sample, y_sample = self._subsample_for_scatter(X, y)
        X_sample_np = X_sample.values if hasattr(X_sample, "values") else X_sample

        # Extract each equation
        for idx, row in selected.iterrows():
            eq_dict = self._row_to_dict(row)
            equations_list.append(eq_dict)
            if self.full_front:
                continue

            # Generate predictions
            scatter = self._generate_scatter(model, row, idx, X_sample, X_sample_np, y_sample)
            if scatter:
                scatter_data[eq_dict["equation"]] = scatter

        logger.info(f"Generated scatter data for {len(scatter_data)} equations")

        # Find best equation
        best_equation = None
        if equations_list:
            sorted_eqs = sorted(equations_list, key=lambda e: e["loss"])
            best_equation = sorted_eqs[0]

        return equations_list, scatter_data, best_equation

    def _subsample_for_scatter(self, X: Any, y: Any) -> tuple[Any, np.ndarray]:
        """Subsample data for scatter plots."""
        y_values = y.values if hasattr(y, "values") else y

        if len(y_values) > self.max_scatter_points:
            rng = np.random.default_rng(self.seed)
            indices = rng.choice(len(y_values), self.max_scatter_points, replace=False)
            indices = np.sort(indices)
            return X.iloc[indices], y_values[indices]

        return X, y_values

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        """Convert equation row to dictionary."""
        return {
            "equation": str(row.get("equation", "")),
            "complexity": int(row.get("complexity", 0)),
            "loss": float(row.get("loss", float("inf"))),
            "score": float(row.get("score", 0.0)),
            "sympy_format": str(row.get("sympy_format", "")),
        }

    def _generate_scatter(
        self,
        model: Any,
        row: Any,
        idx: int,
        X_sample: Any,
        X_sample_np: np.ndarray,
        y_sample: np.ndarray,
    ) -> dict[str, list[float]] | None:
        """Generate scatter data for an equation."""
        eq_string = str(row.get("equation", ""))

        try:
            if "lambda_format" in row and row["lambda_format"] is not None:
                y_pred = row["lambda_format"](X_sample_np)
            else:
                y_pred = model.predict(X_sample, index=idx)

            if hasattr(y_pred, "values"):
                y_pred = y_pred.values

            return {
                "measured": y_sample.tolist(),
                "predicted": y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred),
            }
        except Exception as e:
            logger.warning(f"Failed scatter for '{eq_string[:50]}...': {e}")
            return None


@TaskRegistry.register("pysr")
class PySRTask(Task):
    """
    PySR symbolic regression task.

    Uses genetic programming to discover mathematical equations
    that fit the relationship between features and target.
    """

    name = "pysr"

    def _validate_input(self, input_data: dict[str, Any]) -> None:
        """Validate PySR task input."""
        required = ["data", "target_column", "predictor_columns"]
        for field in required:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        if not input_data["predictor_columns"]:
            raise ValueError("predictor_columns cannot be empty")

        transform = input_data.get("target_transform")
        if transform and transform not in TARGET_TRANSFORMS:
            raise ValueError(f"Unsupported target_transform: {transform}")

    def _get_config(self, input_data: dict[str, Any]) -> PySRConfig:
        """Extract PySR configuration from input data."""
        config_dict = input_data.get("config", {})
        return PySRConfig(
            niterations=config_dict.get("niterations"),
            populations=config_dict.get("populations", 15),
            population_size=config_dict.get("population_size", 33),
            ncycles_per_iteration=config_dict.get("ncycles_per_iteration", 550),
            binary_operators=config_dict.get("binary_operators", ["+", "-", "*", "/"]),
            unary_operators=config_dict.get("unary_operators", ["exp", "log", "sqrt", "abs"]),
            maxsize=config_dict.get("maxsize", 20),
            maxdepth=config_dict.get("maxdepth", 10),
            timeout_in_seconds=config_dict.get("timeout_in_seconds", 3600),
            parsimony=config_dict.get("parsimony", 0.0032),
            turbo=config_dict.get("turbo", True),
        )

    def _execute(self, input_data: dict[str, Any]) -> TaskResult:
        """Execute PySR symbolic regression."""
        from pysr import PySRRegressor

        self._report(10, "Loading data", "pysr_loading")

        # Parse input
        df_input = DataFrameInput.from_dict(input_data)
        config = self._get_config(input_data)
        run_id = input_data.get("run_id", os.environ.get("SLURM_JOB_ID", "unknown"))

        X, y = df_input.X, df_input.y
        transform = input_data.get("target_transform")
        if transform:
            with np.errstate(all="ignore"):
                y = TARGET_TRANSFORMS[transform](y)
            if not np.all(np.isfinite(y)):
                raise ValueError(f"target_transform={transform} produced non-finite values")
            logger.info(f"Fitting transformed target: {transform}(y)")

        logger.info(f"Loaded data: {df_input.n_rows} rows, {df_input.n_features} predictors")

        self._report(15, "Computing configuration", "pysr_config")

        # Build configuration
        config_builder = PySRConfigBuilder(config)
        niterations = config_builder.get_niterations(X, y)
        constraints, nested_constraints = config_builder.build_constraints()

        # Get CPU count from SLURM allocation or fallback to os.cpu_count()
        cpu_count = int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count() or 4))

        # Set Julia threading to match allocated CPUs
        os.environ["JULIA_NUM_THREADS"] = str(cpu_count)

        # Setup temp directory
        temp_dir = os.path.join(tempfile.gettempdir(), f"pysr_{run_id}")
        os.makedirs(temp_dir, exist_ok=True)

        logger.info(
            f"PySR config: niterations={niterations}, cpus={cpu_count}, julia_threads={cpu_count}"
        )

        self._report(20, "Creating PySR model", "pysr_model")

        extra_kwargs: dict[str, Any] = {}
        guesses = [g for g in input_data.get("guesses") or [] if isinstance(g, str) and g.strip()]
        if guesses:
            if _supports_guesses():
                extra_kwargs["guesses"] = guesses
                logger.info(f"Seeding search with {len(guesses)} guesses")
            else:
                logger.warning("Installed PySR does not support guesses; ignoring them")

        # Create model
        model = PySRRegressor(
            niterations=niterations,
            populations=config.populations,
            population_size=config.population_size,
            ncycles_per_iteration=config.ncycles_per_iteration,
            binary_operators=list(config.binary_operators),
            unary_operators=list(config.unary_operators),
            maxsize=config.maxsize,
            maxdepth=config.maxdepth,
            timeout_in_seconds=config.timeout_in_seconds,
            parsimony=config.parsimony,
            turbo=config.turbo,
            constraints=constraints,
            nested_constraints=nested_constraints,
            extra_sympy_mappings={},
            parallelism="multiprocessing",
            procs=cpu_count,
            verbosity=1,
            progress=True,
            tempdir=temp_dir,
            **extra_kwargs,
        )

        self._report(30, "Running symbolic regression", "pysr_running")
        try:
            model.fit(X, y)
        except Exception as e:
            if "guesses" not in extra_kwargs:
                raise
            # An unparsable guess must not cost the whole search.
            logger.warning(f"Fit with guesses failed ({e}); retrying without them")
            model.set_params(guesses=None)
            model.fit(X, y)

        self._report(85, "Extracting equations", "pysr_extracting")

        # Extract equations
        extractor = EquationExtractor(
            max_scatter_points=config.max_scatter_points,
            seed=config.scatter_seed,
            full_front=bool(input_data.get("return_full_front")),
        )
        equations_list, scatter_data, best_equation = extractor.extract_equations(model, X, y)

        self._report(90, "Finalizing", "pysr_finalizing")

        logger.info(f"PySR completed: {len(equations_list)} equations found")

        return TaskResult.success(
            equations=equations_list,
            best_equation=best_equation,
            iterations_completed=niterations,
            scatter_data=scatter_data,
            target_transform=transform,
        )
