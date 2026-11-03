#!/usr/bin/env python3
"""
Local tester for the compute side of the pipeline.

- ``--task pysr``: run the PySR worker task (needs Julia/PySR installed)
- ``--task classic``: screen the classic function catalog (Mitscherlich, Langmuir,
  power law, ...) with the discovery agent's fitting engine and print each model's
  held-out R2 and diagnosed reasons. No LLM, cluster or database needed.

Usage:
    # Classic-law screen on the soil phosphate example
    python dev/run_worker_task.py --task classic --example 1

    # Run PySR with custom iterations
    python dev/run_worker_task.py --task pysr --example 3 --niterations 10

    # PySR on a log-transformed target, seeded with a guess
    python dev/run_worker_task.py --task pysr --example 3 --target-transform log --guesses "Synapses + Degree"

    # Save output to file
    python dev/run_worker_task.py --task pysr --example 1 --output results.json

    # Use custom data file
    python dev/run_worker_task.py --task classic --data path/to/data.csv --target my_target --predictors "col1,col2,col3"
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Repository root (slurm_worker package and data/ live there)
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from slurm_worker.reporting.reporter import ProgressObserver
from slurm_worker.tasks import TaskRegistry

# Example configurations
EXAMPLES: dict[int, dict[str, Any]] = {
    1: {
        "path": "data/example_1/sample_data.csv",
        "target": "al_p2o5",
        "predictors": ["mehlich3_p", "organic_matter", "usda_soil_type", "lime_content", "ph_kcl"],
        "description": "Soil phosphate prediction (119 rows, 5 features)",
    },
    2: {
        "path": "data/example_2/Summary table.xlsx",
        "target": "Power conversion efficiency [%]",
        "predictors": None,  # Auto-detect numeric columns
        "description": "Perovskite solar cell efficiency (33 rows)",
    },
    3: {
        "path": "data/example_3/Celegans_AggregatedData.csv",
        "target": "Length",
        "predictors": ["Synapses", "Degree"],
        "description": "C. elegans neuron connectome (299 rows, 2 features)",
    },
    4: {
        "path": "data/example_4/grassland_data.csv",
        "target": "GPP",
        "predictors": ["CO2", "AMO", "SD_VPDI", "PDSI", "SMI", "Tm_sprsum", "VPDI", "NAO"],
        "description": "Grassland gross primary production from climate indices (yearly)",
    },
}

# Reduced parameters for quick local testing
PYSR_LOCAL_CONFIG = {
    "niterations": 10,
    "populations": 5,
    "population_size": 20,
    "timeout_in_seconds": 300,
}


class ConsoleReporter(ProgressObserver):
    """Progress reporter that prints to console."""

    def __init__(self, run_id: str = "local-test"):
        self.run_id = run_id

    def on_progress(
        self, progress: int, status: str | None = None, step: str | None = None
    ) -> None:
        """Print progress update to console."""
        message = f"[{progress:3d}%]"
        if status:
            message += f" {status}"
        if step:
            message += f" ({step})"
        print(message)

    def on_error(self, error: str, details: dict[str, Any] | None = None) -> None:
        """Print error to console."""
        print(f"[ERROR] {error}")
        if details:
            print(f"        Details: {details}")

    def on_complete(self, results: dict[str, Any]) -> None:
        """Print completion message to console."""
        print("[DONE] Task completed successfully")


def load_data(path: str) -> pd.DataFrame:
    """
    Load CSV or Excel file.

    Args:
        path: Path to data file

    Returns:
        Loaded DataFrame

    Raises:
        ValueError: If file format is not supported
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    suffix = path_obj.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Use .csv or .xlsx")


def auto_detect_predictors(df: pd.DataFrame, target: str) -> list[str]:
    """
    Auto-detect numeric predictor columns.

    Args:
        df: DataFrame to analyze
        target: Target column name to exclude

    Returns:
        List of numeric column names (excluding target)
    """
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    return [col for col in numeric_cols if col != target]


def dataframe_to_input(df: pd.DataFrame, target: str, predictors: list[str]) -> dict[str, Any]:
    """
    Convert pandas DataFrame to slurm_worker input format.

    Args:
        df: Source DataFrame
        target: Target column name
        predictors: List of predictor column names

    Returns:
        Dictionary in slurm_worker input format
    """
    # Select only target and predictor columns
    columns_to_use = [target, *predictors]
    df_subset = df[columns_to_use].copy()

    return {
        "data": {
            "columns": df_subset.columns.tolist(),
            "index": df_subset.index.tolist(),
            "data": df_subset.values.tolist(),
        },
        "target_column": target,
        "predictor_columns": predictors,
    }


def prepare_input(
    df: pd.DataFrame,
    target: str,
    predictors: list[str] | None,
    niterations: int | None = None,
    target_transform: str | None = None,
    guesses: list[str] | None = None,
) -> dict[str, Any]:
    """
    Prepare input data for the PySR task.

    Args:
        df: Source DataFrame
        target: Target column name
        predictors: List of predictor columns (None to auto-detect)
        niterations: Optional override for PySR iterations
        target_transform: Optional transform of the target (log, log1p, sqrt)
        guesses: Optional seed formulas for the search

    Returns:
        Dictionary ready for task execution
    """
    # Auto-detect predictors if not provided
    if predictors is None:
        predictors = auto_detect_predictors(df, target)
        print(f"Auto-detected predictors: {predictors}")

    # Validate columns exist
    missing = [col for col in [target, *predictors] if col not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in data: {missing}")

    # Build base input
    input_data = dataframe_to_input(df, target, predictors)

    config = PYSR_LOCAL_CONFIG.copy()
    if niterations is not None:
        config["niterations"] = niterations
    input_data["config"] = config
    input_data["target_transform"] = target_transform
    input_data["guesses"] = guesses or []

    return input_data


def run_task(
    task_type: str, input_data: dict[str, Any], reporter: ConsoleReporter
) -> dict[str, Any]:
    """
    Run a task and return results.

    Args:
        task_type: Task type name ("pysr")
        input_data: Prepared input data
        reporter: Progress reporter

    Returns:
        Task results dictionary
    """
    print(f"\n{'=' * 60}")
    print(f"Running {task_type.upper()} task")
    print(f"{'=' * 60}")

    task = TaskRegistry.create(task_type, reporter)
    result = task.run(input_data)
    return result.to_dict()


def print_results(task_type: str, results: dict[str, Any]) -> None:
    """
    Print formatted results to console.

    Args:
        task_type: Task type name
        results: Task results dictionary
    """
    print(f"\n{'-' * 60}")
    print(f"{task_type.upper()} Results")
    print(f"{'-' * 60}")

    if results.get("status") == "error":
        print(f"Error: {results.get('error')}")
        return

    if task_type == "pysr":
        equations = results.get("equations", [])
        print(f"Found {len(equations)} equations:")
        for eq in equations[:5]:
            print(f"  Complexity {eq['complexity']}: {eq['equation']}")
            print(f"    Loss: {eq['loss']:.6f}, Score: {eq['score']:.4f}")

        best = results.get("best_equation")
        if best:
            print(f"\nBest equation: {best['equation']}")


def run_classic_screen(
    df: pd.DataFrame, target: str, predictors: list[str] | None
) -> dict[str, Any]:
    """Screen the classic catalog with the discovery engine and print the leaderboard."""
    from backend.services.discovery.report import json_safe
    from backend.services.discovery.session import DiscoverySession

    if predictors is None:
        predictors = auto_detect_predictors(df, target)
    session = DiscoverySession(df, target, predictors)
    profile = session.profile()
    print(f"\nNoise ceiling (out-of-fold random-forest R2): {profile['noise_ceiling_r2']}")
    print("Feature ranking:", ", ".join(f["alias"] for f in profile["features"]))

    n = session.auto_screen()
    session.final_scoring()
    print(f"\nFitted {n} classic models. Top 10 by held-out R2:")
    ranked = session.ranked_models()
    for i, m in enumerate(ranked[:10], 1):
        r2 = m.holdout["r2"] if m.holdout else m.cv_r2
        print(f"\n{i:2d}. {m.label} on {', '.join(m.features)}  R2={r2:.3f}  [{m.verdict}]")
        print(f"    {m.fitted_expression}")
        for reason in m.reasons[:3]:
            print(f"    - {reason}")
    return json_safe(
        {
            "noise_ceiling_r2": profile["noise_ceiling_r2"],
            "models": [m.to_dict() for m in ranked],
        }
    )


def main():
    parser = argparse.ArgumentParser(
        description="Test slurm_worker tasks locally using example data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen classic laws on soil data (no Julia needed)
  python dev/run_worker_task.py --task classic --example 1

  # Run PySR with limited iterations (faster)
  python dev/run_worker_task.py --task pysr --example 1 --niterations 5

  # Use custom data file
  python dev/run_worker_task.py --task classic --data mydata.csv --target y --predictors "x1,x2,x3"
        """,
    )

    # Task selection
    parser.add_argument(
        "--task",
        choices=["pysr", "classic"],
        required=True,
        help="Task type to run",
    )

    # Data source (mutually exclusive)
    data_group = parser.add_mutually_exclusive_group(required=True)
    data_group.add_argument(
        "--example",
        type=int,
        choices=list(EXAMPLES.keys()),
        help="Use built-in example data (1, 2, or 3)",
    )
    data_group.add_argument(
        "--data",
        type=str,
        help="Path to custom CSV or Excel data file",
    )

    # Custom data options (required when using --data)
    parser.add_argument(
        "--target",
        type=str,
        help="Target column name (required with --data)",
    )
    parser.add_argument(
        "--predictors",
        type=str,
        help="Comma-separated predictor column names (optional with --data)",
    )

    # Task options
    parser.add_argument(
        "--niterations",
        type=int,
        help="Number of PySR iterations (default: 10 for local testing)",
    )
    parser.add_argument(
        "--target-transform",
        choices=["log", "log1p", "sqrt"],
        help="Fit PySR to a transformed target",
    )
    parser.add_argument(
        "--guesses",
        type=str,
        help="Semicolon-separated seed formulas for PySR (column names as variables)",
    )

    # Output options
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to JSON file",
    )

    args = parser.parse_args()

    # Validate custom data arguments
    if args.data and not args.target:
        parser.error("--target is required when using --data")

    # Load data
    if args.example:
        example = EXAMPLES[args.example]
        print(f"Loading example {args.example}: {example['description']}")
        data_path = REPO_ROOT / example["path"]
        df = load_data(str(data_path))
        target = example["target"]
        predictors = example["predictors"]
    else:
        print(f"Loading custom data: {args.data}")
        df = load_data(args.data)
        target = args.target
        predictors = args.predictors.split(",") if args.predictors else None

    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")

    all_results = {}

    if args.task == "classic":
        all_results["classic"] = run_classic_screen(df, target, predictors)
    else:
        input_data = prepare_input(
            df=df,
            target=target,
            predictors=predictors,
            niterations=args.niterations,
            target_transform=args.target_transform,
            guesses=[g.strip() for g in args.guesses.split(";")] if args.guesses else None,
        )
        results = run_task("pysr", input_data, ConsoleReporter())
        all_results["pysr"] = results
        print_results("pysr", results)

    # Save results if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nResults saved to: {output_path}")

    # Exit with error code if any task failed
    if any(r.get("status") == "error" for r in all_results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
