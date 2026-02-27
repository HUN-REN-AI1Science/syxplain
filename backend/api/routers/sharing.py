"""
Sharing endpoints router.

Provides endpoints for creating and managing public share links,
as well as public access to shared runs (no auth required).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from backend.api.dependencies import get_share_service
from backend.core.exceptions import EntityNotFoundError
from backend.core.rate_limit import limiter
from backend.core.security import User, get_current_user
from backend.schemas.responses import (
    MessageResponse,
    PublicRunResponse,
    SharedRunsResponse,
    ShareLinkResponse,
)
from backend.services.share_service import ShareService
from backend.utils.security_utils import safe_content_disposition

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sharing"])


# ============================================================================
# Authenticated Sharing Endpoints
# ============================================================================


@router.get("/api/runs/shared", response_model=SharedRunsResponse)
def get_shared_runs(
    current_user: User = Depends(get_current_user),
    share_service: ShareService = Depends(get_share_service),
):
    """
    Get all runs shared by the current user.

    Returns:
        SharedRunsResponse with list of shared runs
    """
    items = share_service.get_shared_runs(current_user.user_id)
    return SharedRunsResponse(items=items)


@router.post("/api/runs/{run_id}/share", response_model=ShareLinkResponse)
def create_share_link(
    run_id: str,
    current_user: User = Depends(get_current_user),
    share_service: ShareService = Depends(get_share_service),
):
    """
    Generate a public share link for a run.

    If the run is already shared, returns the existing link.

    Args:
        run_id: The run UUID

    Returns:
        ShareLinkResponse with token and URL

    Raises:
        HTTPException: If run not found
    """
    try:
        result = share_service.create_share_link(run_id, current_user.user_id)
        return ShareLinkResponse(**result)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/api/runs/{run_id}/share", response_model=MessageResponse)
def revoke_share_link(
    run_id: str,
    current_user: User = Depends(get_current_user),
    share_service: ShareService = Depends(get_share_service),
):
    """
    Revoke a public share link for a run.

    Args:
        run_id: The run UUID

    Returns:
        MessageResponse with success message

    Raises:
        HTTPException: If run not found
    """
    try:
        share_service.revoke_share_link(run_id, current_user.user_id)
        return MessageResponse(message="Share link revoked")
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


# ============================================================================
# Public Endpoints (No Authentication Required)
# ============================================================================


@router.get("/api/public/{share_token}", response_model=PublicRunResponse)
@limiter.limit("30/minute")
def get_public_run(
    request: Request,  # Required for rate limiting
    share_token: str,
    share_service: ShareService = Depends(get_share_service),
):
    """
    Get public run results by share token (no auth required).

    Args:
        share_token: The public share token

    Returns:
        PublicRunResponse with status and results

    Raises:
        HTTPException: If shared run not found
    """
    try:
        return share_service.get_public_run(share_token)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.get("/api/public/{share_token}/details")
@limiter.limit("30/minute")
def get_public_run_details(
    request: Request,  # Required for rate limiting
    share_token: str,
    share_service: ShareService = Depends(get_share_service),
):
    """
    Get public run details by share token (no auth required).

    Args:
        share_token: The public share token

    Returns:
        Detailed run information

    Raises:
        HTTPException: If shared run not found
    """
    try:
        return share_service.get_public_run_details(share_token)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.get("/api/public/{share_token}/download-csv")
@limiter.limit("30/minute")
def download_public_csv(
    request: Request,  # Required for rate limiting
    share_token: str,
    share_service: ShareService = Depends(get_share_service),
):
    """
    Download the CSV file for a public run (no auth required).

    Args:
        share_token: The public share token

    Returns:
        CSV file with download headers

    Raises:
        HTTPException: If shared run or file not found
    """
    try:
        db_file = share_service.get_public_file(share_token)
        return Response(
            content=db_file.content,
            media_type="text/csv",
            headers={"Content-Disposition": safe_content_disposition(db_file.filename)},
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
