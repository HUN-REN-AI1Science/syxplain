"""
File handling for task I/O.

Provides a clean interface for reading input and writing output files.
"""

import json
from pathlib import Path
from typing import Any

from slurm_worker.logging_config import get_logger

logger = get_logger("io")


class FileHandler:
    """
    Handles file I/O operations for tasks.

    Encapsulates JSON serialization/deserialization and error handling.
    """

    @staticmethod
    def read_input(path: str) -> dict[str, Any]:
        """
        Read input JSON file.

        Args:
            path: Path to input file

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If JSON is invalid
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

        logger.info(f"Reading input from: {path}")
        with open(file_path) as f:
            return json.load(f)

    @staticmethod
    def write_output(path: str, data: dict[str, Any], indent: int = 2) -> None:
        """
        Write output JSON file.

        Args:
            path: Path to output file
            data: Data to write
            indent: JSON indentation
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Writing output to: {path}")
        with open(file_path, "w") as f:
            json.dump(data, f, indent=indent)

    @staticmethod
    def write_error(path: str, error: str, traceback: str = "") -> None:
        """
        Write error output file.

        Args:
            path: Path to output file
            error: Error message
            traceback: Stack trace
        """
        error_data = {
            "status": "error",
            "error": error,
        }
        if traceback:
            error_data["traceback"] = traceback

        try:
            FileHandler.write_output(path, error_data)
        except Exception as e:
            logger.error(f"Failed to write error output: {e}")
