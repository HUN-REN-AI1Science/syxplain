"""
Error classification for failed analysis runs.

Maps the many ways a run can fail (LLM errors, data problems, cluster
issues, compute crashes) to a stable category and a user-friendly
message. Categories are consumed by the frontend to show targeted
"what went wrong / what you can do" feedback on failed runs.
"""

import re
import traceback as tb_module
from typing import Any


class ErrorCategory:
    """Stable error category identifiers (mirrored in the frontend)."""

    LLM_AUTH = "llm_auth"
    LLM_QUOTA = "llm_quota"
    LLM_MODEL = "llm_model"
    LLM_UNAVAILABLE = "llm_unavailable"
    DATA = "data"
    CLUSTER_SUBMIT = "cluster_submit"
    CLUSTER = "cluster"
    RESOURCE_MEMORY = "resource_memory"
    RESOURCE_TIMEOUT = "resource_timeout"
    COMPUTE = "compute"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


def classify_exception(exc: Exception) -> tuple[str, str]:
    """
    Classify an exception into (category, user-facing message).

    Handles litellm exceptions with friendly messages; falls back to
    message-based heuristics for everything else.
    """
    try:
        import litellm

        if isinstance(exc, litellm.AuthenticationError):
            return ErrorCategory.LLM_AUTH, (
                "API key authentication failed. "
                "Please check that your API key is valid and has not been revoked."
            )
        if isinstance(exc, litellm.RateLimitError):
            return ErrorCategory.LLM_QUOTA, (
                "API rate limit or quota exceeded. "
                "Your API account may have insufficient credits or has hit its usage limit. "
                "Please check your account balance and try again."
            )
        if isinstance(exc, litellm.BudgetExceededError):
            return ErrorCategory.LLM_QUOTA, (
                "API budget exceeded. "
                "Your API account has reached its spending limit. "
                "Please increase your budget or add credits and try again."
            )
        if isinstance(exc, litellm.NotFoundError):
            return ErrorCategory.LLM_MODEL, (
                "The selected AI model was not found. "
                "It may have been deprecated or renamed. "
                "Please try a different model."
            )
        if isinstance(exc, litellm.APIConnectionError):
            return ErrorCategory.LLM_UNAVAILABLE, (
                "Could not connect to the AI service. "
                "Please check your internet connection and try again."
            )
        if isinstance(exc, litellm.Timeout):
            return ErrorCategory.LLM_UNAVAILABLE, (
                "The AI service request timed out. "
                "This may be due to high demand. Please try again later."
            )
    except ImportError:
        pass

    message = str(exc) or exc.__class__.__name__
    return classify_error_message(message), message


def classify_error_message(message: str) -> str:
    """
    Classify a raw error message string into a category.

    Used for errors that arrive as text (e.g. worker callbacks) where
    the original exception object is not available.
    """
    lower = message.lower()

    if re.search(r"out.of.memory|memoryerror|oom.kill|cannot allocate memory", lower):
        return ErrorCategory.RESOURCE_MEMORY
    if re.search(r"time.?limit|timed out|timeout|did not complete within|deadline", lower):
        return ErrorCategory.RESOURCE_TIMEOUT
    if re.search(r"failed to submit|slurm|cluster|slurmrestd|qos|quota", lower):
        return ErrorCategory.CLUSTER
    if re.search(
        r"missing required field|not found in dataset|cannot be empty|column|nan|"
        r"parse|invalid data|expected \d+d array|file .* not found|dataframe|dtype",
        lower,
    ):
        return ErrorCategory.DATA
    if re.search(r"api key|authentication|unauthorized", lower):
        return ErrorCategory.LLM_AUTH
    if re.search(r"rate limit|budget|insufficient credits", lower):
        return ErrorCategory.LLM_QUOTA
    if re.search(r"shap|pysr|julia|sklearn|xgboost|regression", lower):
        return ErrorCategory.COMPUTE
    return ErrorCategory.INTERNAL


# Slurm terminal job states mapped to (category, human description).
# Covers states where slurmrestd reports no usable "reason" string,
# which previously produced messages like "SHAP task failed: None".
_JOB_STATE_FAILURES: dict[str, tuple[str, str]] = {
    "OUT_OF_MEMORY": (
        ErrorCategory.RESOURCE_MEMORY,
        "ran out of memory on the computing cluster. "
        "Your dataset may be too large — try reducing the number of rows or features.",
    ),
    "TIMEOUT": (
        ErrorCategory.RESOURCE_TIMEOUT,
        "exceeded the computing cluster's time limit. Try a smaller dataset or fewer features.",
    ),
    "DEADLINE": (
        ErrorCategory.RESOURCE_TIMEOUT,
        "exceeded the computing cluster's time limit. Try a smaller dataset or fewer features.",
    ),
    "NODE_FAIL": (
        ErrorCategory.CLUSTER,
        "was interrupted by a compute node failure on the cluster. "
        "This is a temporary infrastructure problem — please try again.",
    ),
    "BOOT_FAIL": (
        ErrorCategory.CLUSTER,
        "could not start on the computing cluster. "
        "This is a temporary infrastructure problem — please try again.",
    ),
    "PREEMPTED": (
        ErrorCategory.CLUSTER,
        "was preempted by a higher-priority job on the cluster. Please try again.",
    ),
}


def describe_job_failure(
    task_name: str, state: str, reason: str | None = None, error: str | None = None
) -> tuple[str, str]:
    """
    Build (category, user message) for a Slurm job that ended in a
    non-COMPLETED state.

    Args:
        task_name: Human-readable task name ("SHAP" or "PySR")
        state: Terminal JobState value (e.g. "FAILED", "OUT_OF_MEMORY")
        reason: Slurm-reported reason string, if any
        error: Error string already extracted for the job, if any

    Returns:
        (category, message) tuple
    """
    mapped = _JOB_STATE_FAILURES.get(state)
    if mapped:
        category, description = mapped
        message = f"The {task_name} computation {description}"
        if reason:
            message += f" (cluster reported: {reason})"
        return category, message

    detail = error or reason
    if detail:
        return classify_error_message(detail), f"{task_name} computation failed: {detail}"
    return (
        ErrorCategory.COMPUTE,
        f"The {task_name} computation failed on the cluster without a specific "
        f"error message (job state: {state}).",
    )


def build_error_details(
    category: str,
    stage: str | None = None,
    exc: Exception | None = None,
    traceback: str | None = None,
    task_type: str | None = None,
) -> dict[str, Any]:
    """
    Build the structured error_details dict persisted on the Run record.
    """
    details: dict[str, Any] = {"category": category}
    if stage:
        details["stage"] = stage
    if task_type:
        details["task_type"] = task_type
    if exc is not None:
        details["technical"] = f"{exc.__class__.__name__}: {exc}"
        if traceback is None:
            traceback = "".join(tb_module.format_exception(type(exc), exc, exc.__traceback__))
    if traceback:
        # Cap traceback size to keep the JSONB column reasonable
        details["traceback"] = traceback[-8000:]
    return details
