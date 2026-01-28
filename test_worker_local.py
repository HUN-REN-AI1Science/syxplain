#!/usr/bin/env python3
"""
Local tester for slurm_worker tasks.

Run SHAP and PySR tasks locally using example data from the data/ folder.

Usage:
    # Run SHAP task on example 1
    python test_worker_local.py --task shap --example 1

    # Run PySR task with custom iterations
    python test_worker_local.py --task pysr --example 3 --niterations 10

    # Run both tasks
    python test_worker_local.py --task both --example 1

    # Save output to file
    python test_worker_local.py --task shap --example 1 --output results.json

    # Use custom data file
    python test_worker_local.py --task shap --data path/to/data.csv --target my_target --predictors "col1,col2,col3"
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Add slurm_worker to path
sys.path.insert(0, str(Path(__file__).parent))

from slurm_worker.tasks import TaskRegistry
from slurm_worker.reporting.reporter import ProgressObserver


# Example configurations
EXAMPLES: Dict[int, Dict[str, Any]] = {
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
}

# Reduced parameters for quick local testing
SHAP_LOCAL_CONFIG = {
    "subsample_fraction": 0.5,
    "subsample_min": 50,
    "subsample_max": 500,
    "generate_visualizations": False,
}

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

    def on_progress(self, progress: int, status: Optional[str] = None, step: Optional[str] = None) -> None:
        """Print progress update to console."""
        message = f"[{progress:3d}%]"
        if status:
            message += f" {status}"
        if step:
            message += f" ({step})"
        print(message)

    def on_error(self, error: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Print error to console."""
        print(f"[ERROR] {error}")
        if details:
            print(f"        Details: {details}")

    def on_complete(self, results: Dict[str, Any]) -> None:
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


def auto_detect_predictors(df: pd.DataFrame, target: str) -> List[str]:
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


def dataframe_to_input(df: pd.DataFrame, target: str, predictors: List[str]) -> Dict[str, Any]:
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
    columns_to_use = [target] + predictors
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
    predictors: Optional[List[str]],
    task_type: str,
    niterations: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Prepare input data for a specific task.

    Args:
        df: Source DataFrame
        target: Target column name
        predictors: List of predictor columns (None to auto-detect)
        task_type: Task type ("shap" or "pysr")
        niterations: Optional override for PySR iterations

    Returns:
        Dictionary ready for task execution
    """
    # Auto-detect predictors if not provided
    if predictors is None:
        predictors = auto_detect_predictors(df, target)
        print(f"Auto-detected predictors: {predictors}")

    # Validate columns exist
    missing = [col for col in [target] + predictors if col not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in data: {missing}")

    # Build base input
    input_data = dataframe_to_input(df, target, predictors)

    # Add task-specific configuration
    if task_type == "shap":
        input_data.update(SHAP_LOCAL_CONFIG)
    elif task_type == "pysr":
        config = PYSR_LOCAL_CONFIG.copy()
        if niterations is not None:
            config["niterations"] = niterations
        input_data["config"] = config

    return input_data


def run_task(task_type: str, input_data: Dict[str, Any], reporter: ConsoleReporter) -> Dict[str, Any]:
    """
    Run a task and return results.

    Args:
        task_type: Task type name ("shap" or "pysr")
        input_data: Prepared input data
        reporter: Progress reporter

    Returns:
        Task results dictionary
    """
    print(f"\n{'='*60}")
    print(f"Running {task_type.upper()} task")
    print(f"{'='*60}")

    task = TaskRegistry.create(task_type, reporter)
    result = task.run(input_data)
    return result.to_dict()


def print_results(task_type: str, results: Dict[str, Any]) -> None:
    """
    Print formatted results to console.

    Args:
        task_type: Task type name
        results: Task results dictionary
    """
    print(f"\n{'-'*60}")
    print(f"{task_type.upper()} Results")
    print(f"{'-'*60}")

    if results.get("status") == "error":
        print(f"Error: {results.get('error')}")
        return

    if task_type == "shap":
        interactions = results.get("interactions", [])
        print(f"Top {len(interactions)} interactions:")
        for i, pair in enumerate(interactions[:10], 1):
            print(f"  {i}. {pair['feature1']} x {pair['feature2']}: {pair['interaction_strength']:.4f}")

        print(f"\nTop features: {results.get('top_features', [])}")
        print(f"Samples used: {results.get('samples_used')}")
        print(f"Coverage: {results.get('covered_mass_percent', 0):.1f}%")

    elif task_type == "pysr":
        equations = results.get("equations", [])
        print(f"Found {len(equations)} equations:")
        for eq in equations[:5]:
            print(f"  Complexity {eq['complexity']}: {eq['equation']}")
            print(f"    Loss: {eq['loss']:.6f}, Score: {eq['score']:.4f}")

        best = results.get("best_equation")
        if best:
            print(f"\nBest equation: {best['equation']}")


def main():
    parser = argparse.ArgumentParser(
        description="Test slurm_worker tasks locally using example data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run SHAP on soil data
  python test_worker_local.py --task shap --example 1

  # Run PySR with limited iterations (faster)
  python test_worker_local.py --task pysr --example 1 --niterations 5

  # Run both tasks
  python test_worker_local.py --task both --example 1

  # Use custom data file
  python test_worker_local.py --task shap --data mydata.csv --target y --predictors "x1,x2,x3"
        """,
    )

    # Task selection
    parser.add_argument(
        "--task",
        choices=["shap", "pysr", "both"],
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
        data_path = Path(__file__).parent / example["path"]
        df = load_data(str(data_path))
        target = example["target"]
        predictors = example["predictors"]
    else:
        print(f"Loading custom data: {args.data}")
        df = load_data(args.data)
        target = args.target
        predictors = args.predictors.split(",") if args.predictors else None

    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")

    # Create reporter
    reporter = ConsoleReporter()

    # Determine which tasks to run
    tasks_to_run = ["shap", "pysr"] if args.task == "both" else [args.task]

    all_results = {}

    for task_type in tasks_to_run:
        # Prepare input
        input_data = prepare_input(
            df=df,
            target=target,
            predictors=predictors,
            task_type=task_type,
            niterations=args.niterations,
        )

        # Run task
        results = run_task(task_type, input_data, reporter)
        all_results[task_type] = results

        # Print results
        print_results(task_type, results)

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
