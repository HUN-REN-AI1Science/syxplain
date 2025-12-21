"""
Run management endpoints router.

Provides endpoints for creating, listing, and managing analysis runs.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.api.dependencies import get_run_service
from backend.core.security import User, get_current_user
from backend.core.exceptions import (
    ConfigurationError,
    EntityNotFoundError,
    ValidationError,
)
from backend.services.run_service import RunService
from backend.schemas.requests import RunRequest
from backend.schemas.responses import (
    PaginatedRunsResponse,
    RunResponse,
    RunStatusResponse,
    RunSummary,
    MessageResponse,
)
from backend.workers.analysis_worker import start_analysis_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Runs"])


@router.post(
    "/run",
    response_model=RunResponse
)
def run_analysis(
    request: RunRequest,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
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
        # Validate the request
        run_service.validate_run_request(
            csv_filename=request.csv_filename,
            target_variable=request.problem_description.target_variable,
            features=request.problem_description.features,
            analysis_type=request.analysis_type,
            deep_research_model=request.deep_research_model,
            user_id=current_user.user_id
        )

        # Start the analysis run
        run_id = start_analysis_run(
            problem_desc=request.problem_description.model_dump(),
            csv_filename=request.csv_filename,
            user_id=current_user.user_id,
            analysis_type=request.analysis_type,
            deep_research_model=request.deep_research_model
        )

        logger.info(
            f"Analysis started with Run ID: {run_id} "
            f"(analysis_type={request.analysis_type}, model={request.deep_research_model})"
        )

        return RunResponse(
            run_id=run_id,
            status="pending",
            message="Analysis started"
        )

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e.message}")
        raise HTTPException(status_code=500, detail=e.message)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)


@router.get(
    "/runs",
    response_model=PaginatedRunsResponse
)
def list_runs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_field: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    status: Optional[str] = Query(None, description="Filter by status"),
    analysis_type: Optional[str] = Query(None, description="Filter by analysis type"),
    search: Optional[str] = Query(None, description="Search in filename and target variable"),
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
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
        sort_field=sort_field,
        sort_order=sort_order,
        status=status,
        analysis_type=analysis_type,
        search=search
    )

    # Convert to response format
    items = []
    for run in result.items:
        items.append(RunSummary(
            id=str(run.id),
            status=run.status,
            created_at=run.created_at,
            csv_filename=run.csv_filename,
            target_variable=run.target_variable,
            progress=run.progress or 0,
            analysis_type=run.analysis_type or "quick"
        ))

    return PaginatedRunsResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse
)
def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
):
    """
    Get run status for polling.

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


@router.delete(
    "/runs/{run_id}",
    response_model=MessageResponse
)
def delete_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
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
        raise HTTPException(status_code=500, detail=f"Failed to delete run: {str(e)}")


@router.get("/runs/{run_id}/details")
def get_run_details(
    run_id: str,
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
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
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
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
    current_user: User = Depends(get_current_user),
    run_service: RunService = Depends(get_run_service)
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
            headers={"Content-Disposition": f"attachment; filename={db_file.filename}"}
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
