"""
Feedback endpoint router.

Provides an endpoint for users to submit bug reports and feature requests.
"""

import logging

from fastapi import APIRouter, Depends, Request

from backend.core.rate_limit import limiter
from backend.core.security import User, get_current_user
from backend.schemas.requests import FeedbackRequest
from backend.schemas.responses import FeedbackResponse
from backend.services.feedback_service import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit("10/minute")
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Submit user feedback (bug report or feature request).

    Optionally creates a GitHub issue when configured.
    Rate limited to 5 requests per minute per user.
    """
    service = FeedbackService()
    result = service.submit_feedback(
        category=body.category,
        title=body.title,
        description=body.description,
        user_email=current_user.email,
        user_id=current_user.user_id,
        context=body.context,
    )
    return FeedbackResponse(**result)
