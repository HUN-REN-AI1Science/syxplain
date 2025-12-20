"""
Configuration endpoints router.

Provides endpoints for retrieving application configuration
such as progress phases and available models.
"""
import logging

from fastapi import APIRouter

from backend.core.config import get_settings
from backend.schemas.responses import DeepResearchModelsResponse

# Import progress config loading from logger module
from logger import get_cached_progress_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Configuration"])


@router.get("/progress-config")
def get_progress_config():
    """
    Returns progress phase configuration for frontend progress bar.

    Returns:
        Dictionary with 'phases' list containing phase configuration
    """
    phases, _ = get_cached_progress_config()
    return {"phases": phases}


@router.get(
    "/config/deep-research-models",
    response_model=DeepResearchModelsResponse
)
def get_deep_research_models():
    """
    Returns available deep research models from environment configuration.

    Returns:
        DeepResearchModelsResponse with list of available models
    """
    settings = get_settings()
    models = settings.llm.get_deep_research_model_list()
    return DeepResearchModelsResponse(models=models)
