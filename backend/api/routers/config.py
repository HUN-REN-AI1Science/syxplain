"""
Configuration endpoints router.

Provides endpoints for retrieving application configuration
such as available models.
"""

import logging

from fastapi import APIRouter

from backend.core.config import get_settings
from backend.schemas.responses import UserApiModelsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Configuration"])


@router.get("/config/user-api-models", response_model=UserApiModelsResponse)
def get_user_api_models():
    """
    Returns available models for user-provided API keys.

    Returns:
        UserApiModelsResponse with list of available models
    """
    settings = get_settings()
    models = settings.llm.get_user_api_model_list()
    return UserApiModelsResponse(models=models)
