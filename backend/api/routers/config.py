"""
Configuration endpoints router.

Provides endpoints for retrieving application configuration
such as progress phases and available models.
"""

import logging

from fastapi import APIRouter

from backend.core.config import get_settings
from backend.schemas.responses import DeepResearchModelsResponse, UserApiModelsResponse
from backend.services.progress_service import get_progress_phases

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Configuration"])


@router.get("/progress-config")
def get_progress_config():
    """
    Returns progress phase configuration for frontend progress bar.

    Returns:
        Dictionary with 'phases' list containing phase configuration
    """
    phases = get_progress_phases()
    return {"phases": phases}


@router.get("/config/deep-research-models", response_model=DeepResearchModelsResponse)
def get_deep_research_models():
    """
    Returns available deep research models from environment configuration.

    Returns:
        DeepResearchModelsResponse with list of available models
    """
    settings = get_settings()
    models = settings.llm.get_deep_research_model_list()
    return DeepResearchModelsResponse(models=models)


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
