"""
File upload endpoints router.

Provides endpoints for uploading and validating CSV/Excel files.
"""
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from backend.api.dependencies import get_file_repository, get_file_service_dep
from backend.core.security import User, get_current_user
from backend.core.exceptions import FileValidationError, FileTooLargeError
from backend.core.rate_limit import limiter
from backend.repositories.file_repository import FileRepository
from backend.services.file_service import FileService
from backend.schemas.responses import FileUploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Files"])


@router.post(
    "/upload",
    response_model=FileUploadResponse
)
@limiter.limit("10/minute")  # Rate limit: 10 uploads per minute per IP
def upload_file(
    request: Request,  # Required for rate limiting
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service_dep),
    file_repo: FileRepository = Depends(get_file_repository)
):
    """
    Upload a CSV or Excel file for analysis.

    Validates the file extension, size, and content.
    Returns column information for configuration.

    Args:
        file: The uploaded file

    Returns:
        FileUploadResponse with column information

    Raises:
        HTTPException: If validation fails
    """
    logger.info(f"User {current_user.user_id} uploading file: {file.filename}")

    try:
        # Process the upload (validates and extracts metadata)
        content, metadata = file_service.process_upload(
            file.file,
            file.filename
        )

        # Store in database
        file_repo.create_file(
            filename=file.filename,
            content=content,
            user_id=current_user.user_id,
            media_type=metadata.media_type
        )

        return FileUploadResponse(
            filename=metadata.filename,
            columns=metadata.columns,
            column_types=metadata.column_types,
            nan_counts=metadata.nan_counts
        )

    except FileTooLargeError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except FileValidationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"File upload failed for {file.filename}: {e}")
        raise HTTPException(status_code=400, detail=f"File upload failed: {str(e)}")
