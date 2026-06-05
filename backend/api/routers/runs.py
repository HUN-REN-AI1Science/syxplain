"""
Run management endpoints router.

Provides endpoints for creating, listing, and managing analysis runs.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.api.dependencies import get_run_service
from backend.core.constants import RunStatus
from backend.core.exceptions import (
    ConfigurationError,
    EntityNotFoundError,
    ValidationError,
)
from backend.core.security import User, get_current_user_jwt_only
from backend.schemas.requests import RunRequest, SortField, SortOrder
from backend.schemas.responses import (
    MessageResponse,
    PaginatedRunsResponse,
    RunResponse,
    RunStatusResponse,
    RunSummary,
)
from backend.services.analysis_service import start_analysis_run
from backend.services.progress_service import get_progress_phases
from backend.services.run_service import RunService
from backend.utils.security_utils import safe_content_disposition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Runs"])


_slurm_health_cache: dict[str, float | bool] = {"ts": 0.0, "ok": False}
_SLURM_HEALTH_TTL = 30.0  # seconds


async def _check_slurm_reachable() -> bool:
    """Check slurmrestd is reachable, cached for 30s to avoid per-request overhead."""
    import time

    now = time.monotonic()
    if now - _slurm_health_cache["ts"] < _SLURM_HEALTH_TTL:
        return bool(_slurm_health_cache["ok"])

    import httpx

    from backend.core.config import get_slurm_settings
    from backend.infrastructure.slurm.client import API_VERSION

    try:
        settings = get_slurm_settings()
        if not settings.api_url or not settings.auth_token:
            result = False
        else:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(
                    f"{settings.api_url}/slurm/{API_VERSION}/diag",
                    headers={
                        "Authorization": f"Bearer {settings.auth_token}",
                        "Slurm-User-Name": settings.user_name,
                    },
                )
            result = response.status_code == 200
    except Exception as e:
        logger.debug(f"Slurm pre-flight check failed: {e}")
        result = False

    _slurm_health_cache["ts"] = now
    _slurm_health_cache["ok"] = result
    return result


@router.post("/run", response_model=RunResponse)
async def run_analysis(
    request: RunRequest,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Start a new analysis run.

    Validates the request, creates a run record, and starts
    background processing.

    Args:
        request: Run configuration including problem description

    Returns:
        RunResponse with run_id and status

    Raises:
        HTTPException: If validation fails or configuration is missing
    """
    logger.info(f"User {current_user.user_id} requesting run for file: {request.csv_filename}")

    try:
        # Check user's permission status from JWT roles
        has_hunren_access = current_user.has_hunren_access

        # Extract user API keys if provided
        user_api_key = None
        user_model = None
        user_openai_key = None
        if request.user_api_keys:
            user_api_key = request.user_api_keys.gemini_api_key
            user_model = request.user_api_keys.gemini_model
            user_openai_key = request.user_api_keys.openai_api_key

        # Check Slurm cluster is reachable before accepting the run
        if not await _check_slurm_reachable():
            raise HTTPException(
                status_code=503,
                detail="The computing cluster is temporarily unavailable. Please try again later.",
            )

        # Validate the request with permission context
        run_service.validate_run_request(
            csv_filename=request.csv_filename,
            target_variable=request.problem_description.target_variable,
            features=request.problem_description.features,
            analysis_type=request.analysis_type,
            deep_research_model=request.deep_research_model,
            user_id=current_user.user_id,
            has_hunren_access=has_hunren_access,
            user_api_key=user_api_key,
            user_openai_key=user_openai_key,
        )

        # Start the analysis run with user keys if applicable
        run_id = start_analysis_run(
            problem_desc=request.problem_description.model_dump(),
            csv_filename=request.csv_filename,
            user_id=current_user.user_id,
            analysis_type=request.analysis_type,
            deep_research_model=request.deep_research_model,
            user_api_key=user_api_key if not has_hunren_access else None,
            user_model=user_model if not has_hunren_access else None,
            user_openai_key=user_openai_key if not has_hunren_access else None,
        )

        logger.info(
            f"Analysis started with Run ID: {run_id} "
            f"(analysis_type={request.analysis_type}, model={request.deep_research_model}, "
            f"using_user_key={not has_hunren_access and user_api_key is not None})"
        )

        return RunResponse(
            run_id=run_id,
            status=RunStatus.PENDING,
            message="Analysis started",
            progress_phases=get_progress_phases(),
        )

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e.message}")
        raise HTTPException(status_code=500, detail=e.message)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get("/runs", response_model=PaginatedRunsResponse)
def list_runs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_field: SortField = Query(SortField.CREATED_AT, description="Field to sort by"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order: asc or desc"),
    status: str | None = Query(None, description="Filter by status"),
    analysis_type: str | None = Query(None, description="Filter by analysis type"),
    search: str | None = Query(None, description="Search in filename and target variable"),
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    List runs for the current user with filtering and pagination.

    Args:
        page: Page number (1-indexed)
        page_size: Items per page
        sort_field: Field to sort by
        sort_order: Sort direction
        status: Optional status filter
        analysis_type: Optional analysis type filter
        search: Optional search query

    Returns:
        PaginatedRunsResponse with runs list and pagination info
    """
    result = run_service.list_runs(
        user_id=current_user.user_id,
        page=page,
        page_size=page_size,
        sort_field=sort_field.value,
        sort_order=sort_order.value,
        status=status,
        analysis_type=analysis_type,
        search=search,
    )

    # Convert to response format
    items = []
    for run in result.items:
        items.append(
            RunSummary(
                id=str(run.id),
                status=run.status,
                created_at=run.created_at,
                csv_filename=run.csv_filename,
                target_variable=run.target_variable,
                progress=run.progress or 0,
                analysis_type=run.analysis_type or "quick",
                start_time=run.start_time,
                finish_time=run.finish_time,
            )
        )

    return PaginatedRunsResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Get run details and status.

    Args:
        run_id: The run UUID

    Returns:
        RunStatusResponse with status, progress, results

    Raises:
        HTTPException: If run not found
    """
    try:
        return run_service.get_run_status(run_id, current_user.user_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.post("/runs/{run_id}/cancel", response_model=MessageResponse)
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Cancel a running or pending analysis.

    Returns success even if already completed (idempotent).

    Args:
        run_id: The run UUID

    Returns:
        MessageResponse with success message

    Raises:
        HTTPException: If run not found
    """
    try:
        await run_service.cancel_run(run_id, current_user.user_id)
        return MessageResponse(message="Run cancelled")
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.delete("/runs/{run_id}", response_model=MessageResponse)
def delete_run(
    run_id: str,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Permanently delete a run and all associated data.

    Args:
        run_id: The run UUID

    Returns:
        MessageResponse with success message

    Raises:
        HTTPException: If run not found or deletion fails
    """
    try:
        run_service.delete_run(run_id, current_user.user_id)
        return MessageResponse(message="Run deleted successfully")
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except Exception as e:
        logger.error(f"Failed to delete run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete run: {e!s}")


@router.get("/runs/{run_id}/details")
def get_run_details(
    run_id: str,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Get comprehensive run details including CSV metadata.

    Args:
        run_id: The run UUID

    Returns:
        Detailed run information with file metadata

    Raises:
        HTTPException: If run not found
    """
    try:
        return run_service.get_run_details(run_id, current_user.user_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.get("/runs/{run_id}/download/{filename}")
def download_file(
    run_id: str,
    filename: str,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Download an artifact file from a run.

    Args:
        run_id: The run UUID
        filename: The artifact filename

    Returns:
        File content with appropriate media type

    Raises:
        HTTPException: If run or file not found
    """
    try:
        artifact = run_service.get_artifact(run_id, filename, current_user.user_id)
        return Response(content=artifact.content, media_type=artifact.media_type)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.get("/runs/{run_id}/download-csv")
def download_csv(
    run_id: str,
    current_user: User = Depends(get_current_user_jwt_only),
    run_service: RunService = Depends(get_run_service),
):
    """
    Download the original CSV file associated with a run.

    Args:
        run_id: The run UUID

    Returns:
        CSV file with download headers

    Raises:
        HTTPException: If run or file not found
    """
    try:
        db_file = run_service.get_original_file(run_id, current_user.user_id)
        return Response(
            content=db_file.content,
            media_type="text/csv",
            headers={"Content-Disposition": safe_content_disposition(db_file.filename)},
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
