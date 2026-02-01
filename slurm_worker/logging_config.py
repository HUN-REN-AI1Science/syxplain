"""
Logging configuration for the worker.

Provides consistent logging setup across all modules.
"""

import logging
import sys


def setup_logging(
    level: int = logging.INFO,
    name: str | None = None,
) -> logging.Logger:
    """
    Configure and return a logger.

    Args:
        level: Logging level
        name: Logger name (default: syxplain_worker)

    Returns:
        Configured logger instance
    """
    logger_name = name or "syxplain_worker"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    return logging.getLogger(logger_name)


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger with the given name.

    Args:
        name: Logger name suffix

    Returns:
        Logger instance
    """
    return logging.getLogger(f"syxplain_worker.{name}")
