"""
Command-line interface for the worker.

Handles argument parsing and provides the main entry point.
"""

import argparse
import sys
import time
import traceback

from slurm_worker.config import WorkerConfig
from slurm_worker.io import FileHandler
from slurm_worker.logging_config import get_logger, setup_logging
from slurm_worker.reporting import ProgressReporter
from slurm_worker.tasks import TaskRegistry

logger = get_logger("cli")


def create_parser() -> argparse.ArgumentParser:
    """
    Create argument parser.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="Syxplain Slurm Worker - Execute compute tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --task-type shap --input input.json --output output.json
  %(prog)s --task-type pysr --input input.json --output output.json --run-id abc123
        """,
    )

    parser.add_argument(
        "--task-type",
        required=True,
        choices=TaskRegistry.available_tasks(),
        help="Type of task to execute",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Run ID for progress reporting (default: SLURM_JOB_ID or 'local')",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input JSON file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for output JSON file",
    )
    parser.add_argument(
        "--callback-url",
        default="",
        help="Backend callback URL (overrides CALLBACK_URL env)",
    )
    parser.add_argument(
        "--callback-token",
        default="",
        help="Backend callback token (overrides CALLBACK_TOKEN env)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


class WorkerRunner:
    """
    Orchestrates task execution.

    Follows the Single Responsibility Principle - handles the workflow
    of reading input, executing tasks, and writing output.
    """

    def __init__(self, config: WorkerConfig):
        """
        Initialize runner.

        Args:
            config: Worker configuration
        """
        self.config = config
        self.reporter = ProgressReporter(config.run_id, config.callback)
        self.file_handler = FileHandler()

    def run(self) -> int:
        """
        Execute the task workflow.

        Returns:
            Exit code (0 for success, 1 for failure)
        """
        logger.info(f"Starting {self.config.task_type} task for run {self.config.run_id}")
        logger.info(f"Input: {self.config.input_path}")
        logger.info(f"Output: {self.config.output_path}")

        start_time = time.time()

        try:
            return self._execute_task(start_time)
        except Exception as e:
            return self._handle_error(e, start_time)

    def _execute_task(self, start_time: float) -> int:
        """Execute the task and write results."""
        # Read input
        self.reporter.on_progress(5, "Reading input", "reading_input")
        input_data = self.file_handler.read_input(self.config.input_path)

        # Create and run task
        task = TaskRegistry.create(self.config.task_type, self.reporter)
        result = task.run(input_data)

        # Check for task failure
        if result.status == "error":
            raise RuntimeError(result.error or "Task failed")

        # Add timing info
        elapsed = time.time() - start_time
        result_dict = result.to_dict()
        result_dict["computation_time_seconds"] = elapsed

        # Write output
        self.reporter.on_progress(95, "Writing output", "writing_output")
        self.file_handler.write_output(self.config.output_path, result_dict)

        # Report completion
        self.reporter.on_progress(100, "Task completed", "completed")
        self.reporter.on_complete(result_dict)

        logger.info(f"Task completed successfully in {elapsed:.1f}s")
        return 0

    def _handle_error(self, error: Exception, start_time: float) -> int:
        """Handle task failure."""
        error_msg = str(error)
        error_trace = traceback.format_exc()
        elapsed = time.time() - start_time

        logger.error(f"Task failed after {elapsed:.1f}s: {error_msg}")
        logger.error(error_trace)

        # Report error
        self.reporter.on_error(error_msg, {"traceback": error_trace})

        # Write error output
        self.file_handler.write_error(
            self.config.output_path,
            error_msg,
            error_trace,
        )

        return 1


def main(argv: list | None = None) -> int:
    """
    Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv)

    Returns:
        Exit code
    """
    # Setup logging first
    setup_logging()

    # Parse arguments
    parser = create_parser()
    args = parser.parse_args(argv)

    # Create configuration
    config = WorkerConfig.from_args(args)

    # Run worker
    runner = WorkerRunner(config)
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
