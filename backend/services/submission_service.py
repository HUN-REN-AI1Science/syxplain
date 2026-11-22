"""
Submitting an analysis in one step: dataset plus parameters in, run id out.

Shared by the programmatic API (POST /api/v1/analyze) and the MCP server, so both
validate and start a run the same way.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from backend.core.exceptions import ComputeUnavailableError
from backend.core.security import User
from backend.infrastructure.slurm.health import is_slurm_reachable
from backend.repositories.file_repository import FileRepository
from backend.schemas.programmatic import AnalyzeParams
from backend.services.analysis_service import start_analysis_run
from backend.services.file_service import FileMetadata
from backend.services.run_service import RunService

logger = logging.getLogger(__name__)


@dataclass
class Submission:
    """An accepted analysis."""

    run_id: str
    row_count: int
    # Columns renamed to valid identifiers: {name in the file: name used in the results}
    renamed_columns: dict[str, str] = field(default_factory=dict)


def resolve_column_names(
    target_variable: str, features: dict[str, str], renamed_columns: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """
    Translate column names as written in the file to the stored (sanitized) names,
    so a caller can use either form.
    """
    target = renamed_columns.get(target_variable, target_variable)
    return target, {renamed_columns.get(name, name): desc for name, desc in features.items()}


def _read_dataset(
    file_obj, filename: str, params: AnalyzeParams, run_service: RunService
) -> tuple[bytes, FileMetadata, str, dict[str, str]]:
    """Parse the dataset and check the requested columns. Blocking."""
    file_service = run_service.file_service
    content, metadata, df = file_service.process_upload(file_obj, filename)
    target, features = resolve_column_names(
        params.target_variable, params.features, metadata.renamed_columns
    )
    file_service.validate_columns_exist(df, target, features)
    return content, metadata, target, features


async def submit_analysis(
    *,
    user: User,
    filename: str,
    file_obj,
    params: AnalyzeParams,
    run_service: RunService,
    file_repo: FileRepository,
) -> Submission:
    """
    Validate a dataset and its parameters, store the dataset and start the run.
    Nothing is stored when any check fails.

    Callers with server-key access always run on the server's LLM keys; any LLM
    settings in ``params`` are then ignored.

    Raises:
        FileValidationError, FileTooLargeError: unusable dataset or unknown columns
        ValidationError: missing or unsafe LLM settings
        TooManyActiveRunsError: the account is at its limit of active runs
        ComputeUnavailableError: the cluster cannot be reached
        ConfigurationError: server keys are not configured
    """
    user_llm = None if user.has_server_keys_access else params.to_user_llm()

    # The checks that need no dataset first, so a refused request costs no parsing
    await asyncio.to_thread(
        run_service.check_can_start, user.user_id, user.has_server_keys_access, user_llm
    )
    if not await is_slurm_reachable():
        raise ComputeUnavailableError()

    # Blocking (file parsing, database): off the event loop
    content, metadata, target, features = await asyncio.to_thread(
        _read_dataset, file_obj, filename, params, run_service
    )
    stored = await asyncio.to_thread(
        file_repo.create_file,
        filename=metadata.filename,
        content=content,
        user_id=user.user_id,
        media_type=metadata.media_type,
    )
    run_id = start_analysis_run(
        problem_desc={
            "project_description": params.project_description,
            "target_variable": target,
            "features": features,
        }
        | ({"literature_text": params.literature_text} if params.literature_text else {})
        | ({} if params.web_literature else {"web_literature": False}),
        csv_filename=metadata.filename,
        user_id=user.user_id,
        user_llm=user_llm,
        file_id=str(stored.id),
    )
    logger.info(f"Run {run_id} submitted for user {user.user_id}")
    return Submission(
        run_id=run_id,
        row_count=metadata.row_count,
        renamed_columns=metadata.renamed_columns,
    )
