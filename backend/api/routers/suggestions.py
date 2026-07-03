"""
Suggestion endpoints router.

Provides automatic column description suggestions using a small LLM.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.core.config import get_settings
from backend.core.rate_limit import limiter
from backend.core.security import User, get_current_user_jwt_only
from backend.schemas.requests import SuggestDescriptionsRequest
from backend.schemas.responses import SuggestDescriptionsResponse
from backend.services.llm_service import suggest_column_descriptions
from backend.utils.validation import validate_gemini_key_format

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Suggestions"])


@router.post("/suggest-descriptions", response_model=SuggestDescriptionsResponse)
@limiter.limit("10/minute")
async def suggest_descriptions(
    request: Request,
    body: SuggestDescriptionsRequest,
    current_user: User = Depends(get_current_user_jwt_only),
):
    """
    Suggest short descriptions for dataset columns based on the problem description.

    HUN-REN members use the server's small model; other users must provide
    their own Gemini API key (server keys are never used on their behalf).

    Returns:
        SuggestDescriptionsResponse with descriptions and any failed columns

    Raises:
        HTTPException: 400 if a required/invalid key, 502 if generation fails entirely
    """
    settings = get_settings().llm

    if current_user.has_hunren_access:
        user_api_key = None
        user_model = None
        model = settings.small_model_name
    else:
        if not body.gemini_api_key:
            raise HTTPException(
                status_code=400,
                detail="A Gemini API key is required to generate suggestions.",
            )
        is_valid_format, format_error = validate_gemini_key_format(body.gemini_api_key)
        if not is_valid_format:
            logger.warning(f"Invalid Gemini API key format from user {current_user.user_id}")
            raise HTTPException(status_code=400, detail=format_error)
        user_api_key = body.gemini_api_key
        user_model = body.gemini_model
        model = user_model or settings.small_user_model_name

    try:
        descriptions, failed_columns = await suggest_column_descriptions(
            project_description=body.project_description,
            target_variable=body.target_variable or "",
            columns=body.columns,
            user_api_key=user_api_key,
            user_model=user_model,
        )
    except Exception as e:
        logger.error(f"Column description suggestion failed for user {current_user.user_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail="Suggestion generation failed. Please try again or fill descriptions manually.",
        )

    return SuggestDescriptionsResponse(
        descriptions=descriptions, failed_columns=failed_columns, model=model
    )
