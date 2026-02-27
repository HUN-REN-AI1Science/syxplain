"""
API key management endpoints (internal, JWT-only).

Allows users to generate, view, revoke, and regenerate their single API key
for programmatic access without Keycloak/browser login.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.dependencies import get_api_key_service
from backend.core.exceptions import ValidationError
from backend.core.security import User, get_current_user_jwt_only
from backend.schemas.responses import (
    ApiKeyResponse,
    CreateApiKeyResponse,
    MessageResponse,
)
from backend.services.api_key_service import ApiKeyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/api-keys", response_model=ApiKeyResponse | None)
def get_api_key(
    current_user: User = Depends(get_current_user_jwt_only),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """Get the current user's active API key info, or null if none exists."""
    result = service.get_current_key(current_user.user_id)
    if result is None:
        return None
    return ApiKeyResponse(**result)


@router.post("/api-keys", response_model=CreateApiKeyResponse, status_code=201)
def create_api_key(
    current_user: User = Depends(get_current_user_jwt_only),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """
    Generate a new API key.

    The full key is returned exactly once in the response.
    Store it securely — it cannot be retrieved again.
    """
    try:
        result = service.create_key(user=current_user)
        return CreateApiKeyResponse(**result)
    except ValidationError as e:
        raise HTTPException(status_code=409, detail=e.message)


@router.delete("/api-keys", response_model=MessageResponse)
def revoke_api_key(
    current_user: User = Depends(get_current_user_jwt_only),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """
    Revoke the active API key (soft-delete).

    The key will immediately stop working for authentication.
    """
    try:
        service.revoke_current_key(current_user.user_id)
        return MessageResponse(message="API key revoked")
    except ValidationError as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.post("/api-keys/regenerate", response_model=CreateApiKeyResponse)
def regenerate_api_key(
    current_user: User = Depends(get_current_user_jwt_only),
    service: ApiKeyService = Depends(get_api_key_service),
):
    """
    Regenerate the API key.

    Revokes the old key and creates a new one.
    The new full key is returned exactly once.
    """
    try:
        result = service.regenerate_key(current_user)
        return CreateApiKeyResponse(**result)
    except ValidationError as e:
        raise HTTPException(status_code=404, detail=e.message)
