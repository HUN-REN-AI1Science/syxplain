"""
Pydantic response schemas for API endpoints.

These schemas define the structure of API responses
with proper serialization and documentation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Run Responses
# ============================================================================

class RunResponse(BaseModel):
    """Response when starting a new run."""
    run_id: str
    status: str
    message: str


class RunStatusResponse(BaseModel):
    """Response for run status queries."""
    status: str
    progress: int = Field(ge=0, le=100)
    error: Optional[str] = None
    results: Optional[Dict[str, Any]] = None
    public_share_token: Optional[str] = None
    start_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None


class RunSummary(BaseModel):
    """Summary information for a run in list views."""
    id: str
    status: str
    created_at: datetime
    csv_filename: str
    target_variable: Optional[str] = None
    progress: int = Field(default=0, ge=0, le=100)
    analysis_type: str = "quick"
    start_time: Optional[datetime] = None
    finish_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginatedRunsResponse(BaseModel):
    """Paginated list of runs."""
    items: List[RunSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class CSVMetadata(BaseModel):
    """Metadata about a CSV/Excel file."""
    filename: str
    size_bytes: int
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    columns: List[str] = Field(default_factory=list)


class RunDetailsResponse(BaseModel):
    """Comprehensive run details including file metadata."""
    id: str
    status: str
    created_at: Optional[datetime] = None
    problem_description: Dict[str, Any]
    csv_filename: str
    csv_metadata: Optional[CSVMetadata] = None
    analysis_type: str = "quick"
    error: Optional[str] = None


# ============================================================================
# File Responses
# ============================================================================

class FileUploadResponse(BaseModel):
    """Response after successful file upload."""
    filename: str
    columns: List[str]
    column_types: Dict[str, str]
    nan_counts: Dict[str, int]


# ============================================================================
# Sharing Responses
# ============================================================================

class ShareLinkResponse(BaseModel):
    """Response when creating a share link."""
    share_token: str
    share_url: str


class SharedRunSummary(BaseModel):
    """Summary of a shared run."""
    id: str
    target_variable: Optional[str] = None
    csv_filename: str
    analysis_type: str = "quick"
    created_at: Optional[datetime] = None
    share_token: str
    share_url: str


class SharedRunsResponse(BaseModel):
    """List of shared runs."""
    items: List[SharedRunSummary]


class PublicRunResponse(BaseModel):
    """Public view of a shared run."""
    status: str
    progress: int = Field(ge=0, le=100)
    results: Optional[Dict[str, Any]] = None
    share_token: str


# ============================================================================
# Profile Responses
# ============================================================================

class ProfileResponse(BaseModel):
    """User profile information."""
    email: str
    created_at: Optional[str] = None
    total_runs: int = 0
    total_files: int = 0


class ProfileDeleteResponse(BaseModel):
    """Response after profile deletion."""
    message: str = "Account deleted successfully"


# ============================================================================
# Config Responses
# ============================================================================

class ProgressPhase(BaseModel):
    """Progress phase configuration."""
    name: str
    label: str
    progress_end: int


class ProgressConfigResponse(BaseModel):
    """Progress configuration for frontend."""
    phases: List[ProgressPhase]


class DeepResearchModelsResponse(BaseModel):
    """Available deep research models."""
    models: List[str]


class UserApiModelsResponse(BaseModel):
    """Available models for user-provided API keys."""
    models: List[str]


# ============================================================================
# Error Response
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response format."""
    detail: str
    error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Run not found"
            }
        }


class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


# ============================================================================
# Permission Responses
# ============================================================================

class PermissionResponse(BaseModel):
    """User's permission status."""
    use_hunren_keys: bool
    is_admin: bool = False


class ValidateKeysResponse(BaseModel):
    """Response for API key validation."""
    valid: bool


class UserPermissionInfo(BaseModel):
    """User permission info for admin listing."""
    user_id: str
    email: str
    use_hunren_keys: bool
    granted_by: Optional[str] = None
    user_created_at: Optional[datetime] = None
    permission_updated_at: Optional[datetime] = None


class UsersWithPermissionsResponse(BaseModel):
    """List of users with their permissions."""
    users: List[UserPermissionInfo]


class UpdatePermissionResponse(BaseModel):
    """Response for permission update."""
    success: bool
    user_id: str
    use_hunren_keys: bool
