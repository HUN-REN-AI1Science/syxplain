"""
Suggestion endpoints router.

Provides automatic column description suggestions using a small LLM.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.core.config import get_settings
from backend.core.rate_limit import limiter
from backend.core.security import User, get_current_user_jwt_only
from backend.schemas.requests import SuggestDescriptionsRequest
from backend.schemas.responses import SuggestDescriptionsResponse
from backend.services.llm_service import suggest_column_descriptions
from backend.utils.url_safety import UnsafeUrlError, ensure_public_http_url
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
    their own Gemini or OpenAI-compatible API key (server keys are never used on
    their behalf).

    Returns:
        SuggestDescriptionsResponse with descriptions and any failed columns.
        Per-batch LLM failures are retried once and then reported via
        failed_columns rather than raising.

    Raises:
        HTTPException: 400 for a missing/invalid key, 502 for unexpected errors
    """
    settings = get_settings().llm

    if current_user.has_hunren_access:
        user_llm = None
        model = settings.small_model_name
    else:
        if not body.api_key:
            raise HTTPException(
                status_code=400,
                detail="An API key (Gemini or OpenAI-compatible) is required to generate suggestions.",
            )
        user_llm = body.to_user_llm()
        if body.provider == "gemini":
            is_valid_format, format_error = validate_gemini_key_format(body.api_key)
            if not is_valid_format:
                logger.warning(f"Invalid Gemini API key format from user {current_user.user_id}")
                raise HTTPException(status_code=400, detail=format_error)
        else:
            # The backend will call the user's endpoint: never a private or local address
            try:
                await asyncio.to_thread(ensure_public_http_url, user_llm.api_base)
            except UnsafeUrlError as e:
                raise HTTPException(status_code=400, detail=str(e))
        model = user_llm.small_model(settings.small_user_model_name)

    try:
        descriptions, failed_columns = await suggest_column_descriptions(
            project_description=body.project_description,
            target_variable=body.target_variable or "",
            columns=body.columns,
            user_llm=user_llm,
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
