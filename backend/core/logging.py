"""
Professional logging configuration for the Syxplain backend.

Provides:
- Colorful, human-readable console output using Rich
- Date-folder file rotation for easy debugging
- Sensitive data filtering (never log secrets)
- Proper log level control per module
- Request correlation IDs for tracing
"""

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# Try to use Rich for beautiful console output, fallback to standard if not available
try:
    from rich.console import Console
    from rich.logging import RichHandler

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# ============================================================================
# Constants
# ============================================================================

LOG_DIR = "logs"
LOG_FILENAME = "syxplain.log"

# Patterns for sensitive data that should never be logged
SENSITIVE_PATTERNS = [
    r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^"\'\s]+',
    r'(?i)(secret|api_key|apikey|token|auth|bearer)\s*[=:]\s*["\']?[^"\'\s]+',
    r"(?i)authorization:\s*bearer\s+[^\s]+",
    r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT tokens
]

# Compiled regex for performance
SENSITIVE_REGEX = re.compile("|".join(SENSITIVE_PATTERNS))


# ============================================================================
# Custom Handlers
# ============================================================================


class DateFolderFileHandler(logging.FileHandler):
    """
    File handler that organizes logs into date-stamped folders.

    Creates structure: logs/2025-12-21/syxplain.log
    Automatically rotates to new folder at midnight.
    """

    def __init__(self, base_dir: str, filename: str, mode: str = "a", encoding: str = "utf-8"):
        self.base_dir = Path(base_dir)
        self.filename = filename
        self.current_date = datetime.now().strftime("%Y-%m-%d")

        # Create initial log directory
        log_dir = self.base_dir / self.current_date
        log_dir.mkdir(parents=True, exist_ok=True)

        filepath = log_dir / self.filename
        super().__init__(str(filepath), mode, encoding)

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record, rotating to new folder if date changed."""
        new_date = datetime.now().strftime("%Y-%m-%d")

        if new_date != self.current_date:
            self.current_date = new_date
            self.close()

            # Create new directory
            log_dir = self.base_dir / self.current_date
            log_dir.mkdir(parents=True, exist_ok=True)

            # Update file path
            self.baseFilename = str(log_dir / self.filename)
            self.stream = self._open()

        super().emit(record)


class SensitiveDataFilter(logging.Filter):
    """
    Filter that redacts sensitive data from log messages.

    Prevents accidental logging of passwords, tokens, and API keys.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg:
            record.msg = self._redact(str(record.msg))
        if record.args:
            record.args = tuple(
                self._redact(str(arg)) if isinstance(arg, str) else arg for arg in record.args
            )
        return True

    def _redact(self, text: str) -> str:
        """Replace sensitive data with [REDACTED]."""
        return SENSITIVE_REGEX.sub("[REDACTED]", text)


# ============================================================================
# Formatters
# ============================================================================


class HumanReadableFormatter(logging.Formatter):
    """
    Human-friendly log formatter with aligned columns and context.

    Format: TIMESTAMP | LEVEL | LOGGER | MESSAGE
    """

    LEVEL_COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True):
        self.use_colors = use_colors
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        # Timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Level with padding
        level = record.levelname.ljust(8)

        # Logger name - shorten for readability
        logger_name = self._shorten_name(record.name)

        # Color the level if enabled
        if self.use_colors and sys.stdout.isatty():
            color = self.LEVEL_COLORS.get(record.levelname, "")
            level = f"{color}{level}{self.RESET}"

        # Format message
        message = record.getMessage()

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return f"{timestamp} | {level} | {logger_name:30} | {message}"

    def _shorten_name(self, name: str) -> str:
        """Shorten logger name for readability."""
        # backend.api.routers.runs → api.routers.runs
        if name.startswith("backend."):
            return name[8:]
        return name


# ============================================================================
# Main Configuration
# ============================================================================

_configured = False


def configure_logging(
    log_dir: str = LOG_DIR,
    log_filename: str = LOG_FILENAME,
    level: int = logging.INFO,
    use_rich: bool = True,
) -> None:
    """
    Configure professional logging for the application.

    Args:
        log_dir: Base directory for log files
        log_filename: Name of the log file
        level: Logging level (default INFO)
        use_rich: Use Rich for beautiful console output
    """
    global _configured

    if _configured:
        return  # Prevent duplicate configuration

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers = []

    # Add sensitive data filter to root
    root_logger.addFilter(SensitiveDataFilter())

    # ---- Console Handler ----
    if use_rich and RICH_AVAILABLE:
        console_handler = RichHandler(
            console=Console(force_terminal=True, width=200),
            show_time=True,
            show_path=False,
            rich_tracebacks=False,
            markup=True,
            omit_repeated_times=False,
        )
        console_handler.setLevel(level)
    else:
        # Fallback to standard colored output
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(HumanReadableFormatter(use_colors=True))
        console_handler.setLevel(level)

    root_logger.addHandler(console_handler)

    # ---- File Handler ----
    file_handler = DateFolderFileHandler(log_dir, log_filename)
    file_handler.setFormatter(HumanReadableFormatter(use_colors=False))
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    # ---- Configure Third-Party Loggers ----
    # Reduce noise from verbose libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.INFO)
    logging.getLogger("langgraph").setLevel(logging.INFO)
    logging.getLogger("dspy").setLevel(logging.INFO)
    logging.getLogger("matplotlib.font_manager").setLevel(logging.WARNING)

    _configured = True

    # Log startup message
    log = logging.getLogger(__name__)
    log.info(f"Logging configured: console + {log_dir}/<date>/{log_filename}")


def configure_debug_mode() -> None:
    """
    Enable debug mode for LangChain/LangGraph.

    Call this when you need detailed debugging of AI operations.
    """
    import langchain

    langchain.debug = True
    logging.getLogger("langgraph").setLevel(logging.DEBUG)
    logging.getLogger("langchain").setLevel(logging.DEBUG)
    logging.getLogger(__name__).info("Debug mode enabled for LangChain/LangGraph")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Usage:
        from backend.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    return logging.getLogger(name)


# ============================================================================
# Uvicorn Integration
# ============================================================================


class EndpointFilter(logging.Filter):
    """
    Filter to reduce noise from frequently-called endpoints and mask tokens in URLs.

    Filters out health checks and public endpoints to keep output clean.
    """

    NOISY_PATTERNS = [
        "GET /health",
        "GET /api/runs/",
        "GET /api/public/",
    ]

    # SSE clients pass their JWT as ?token= (EventSource cannot send headers)
    TOKEN_PARAM = re.compile(r"([?&](?:access_)?token=)[^&\s]+")

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn access records: (client, method, path, http_version, status)
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str) and "token=" in path:
                args = list(record.args)
                args[2] = self.TOKEN_PARAM.sub(r"\1***", path)
                record.args = tuple(args)
        message = record.getMessage()
        return not any(pattern in message for pattern in self.NOISY_PATTERNS)


def configure_uvicorn_logging() -> None:
    """Apply custom filtering to uvicorn access logs."""
    logging.getLogger("uvicorn.access").addFilter(EndpointFilter())
