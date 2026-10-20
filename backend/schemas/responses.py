"""
Pydantic response schemas for API endpoints.

These schemas define the structure of API responses
with proper serialization and documentation.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Run Responses
# ============================================================================


class RunResponse(BaseModel):
    """Response when starting a new run."""

    run_id: str
    status: str
    message: str
    progress_phases: list[dict[str, Any]] = Field(default_factory=list)


class RunStatusResponse(BaseModel):
    """Response for run status queries."""

    status: str
    progress: int = Field(ge=0, le=100)
    error: str | None = None
    results: dict[str, Any] | None = None
    public_share_token: str | None = None
    start_time: datetime | None = None
    finish_time: datetime | None = None
    target_variable: str | None = None


class RunSummary(BaseModel):
    """Summary information for a run in list views."""

    id: str
    status: str
    created_at: datetime
    csv_filename: str
    target_variable: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    analysis_type: str = "quick"
    start_time: datetime | None = None
    finish_time: datetime | None = None

    class Config:
        from_attributes = True


class PaginatedRunsResponse(BaseModel):
    """Paginated list of runs."""

    items: list[RunSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class CSVMetadata(BaseModel):
    """Metadata about a CSV/Excel file."""

    filename: str
    size_bytes: int
    row_count: int | None = None
    column_count: int | None = None
    columns: list[str] = Field(default_factory=list)


class RunDetailsResponse(BaseModel):
    """Comprehensive run details including file metadata."""

    id: str
    status: str
    created_at: datetime | None = None
    problem_description: dict[str, Any]
    csv_filename: str
    csv_metadata: CSVMetadata | None = None
    analysis_type: str = "quick"
    error: str | None = None


# ============================================================================
# File Responses
# ============================================================================


class FileUploadResponse(BaseModel):
    """Response after successful file upload."""

    filename: str
    columns: list[str]
    column_types: dict[str, str]
    nan_counts: dict[str, int]


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
    target_variable: str | None = None
    csv_filename: str
    analysis_type: str = "quick"
    created_at: datetime | None = None
    share_token: str
    share_url: str


class SharedRunsResponse(BaseModel):
    """List of shared runs."""

    items: list[SharedRunSummary]


class PublicRunResponse(BaseModel):
    """Public view of a shared run."""

    status: str
    progress: int = Field(ge=0, le=100)
    results: dict[str, Any] | None = None
    share_token: str
    target_variable: str | None = None


# ============================================================================
# Profile Responses
# ============================================================================


class ProfileResponse(BaseModel):
    """User profile information."""

    email: str
    created_at: str | None = None
    total_runs: int = 0
    total_files: int = 0


class ProfileDeleteResponse(BaseModel):
    """Response after profile deletion."""

    message: str = "Account deleted successfully"


# ============================================================================
# API Key Responses
# ============================================================================


class ApiKeyResponse(BaseModel):
    """API key info (never contains the full key)."""

    id: str
    key_prefix: str
    is_active: bool
    created_at: str | None = None
    last_used_at: str | None = None


class CreateApiKeyResponse(BaseModel):
    """Response when creating a new API key. Contains the full key (shown once)."""

    id: str
    key: str = Field(..., description="The full API key — shown only once, store it securely")
    key_prefix: str
    created_at: str | None = None


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

    phases: list[ProgressPhase]


class UserApiModelsResponse(BaseModel):
    """Available models for user-provided API keys."""

    models: list[str]


# ============================================================================
# Error Response
# ============================================================================


class ErrorResponse(BaseModel):
    """Standard error response format."""

    detail: str
    error: str | None = None

    class Config:
        json_schema_extra = {"example": {"detail": "Run not found"}}


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


class SuggestDescriptionsResponse(BaseModel):
    """Response for automatic column description suggestions."""

    descriptions: dict[str, str]
    failed_columns: list[str] = Field(default_factory=list)
    model: str


# ============================================================================
# Admin Dashboard Responses
# ============================================================================


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics."""

    total_users: int
    active_users_24h: int
    total_runs: int
    runs_today: int
    success_rate: float
    avg_duration_seconds: float
    pending_runs: int
    running_runs: int


class RunTrendItem(BaseModel):
    """Single day run trend data."""

    date: str
    total: int
    completed: int
    failed: int
    timeout: int
    cancelled: int


class RunTrendsResponse(BaseModel):
    """Run trends over time."""

    items: list[RunTrendItem]


class StatusDistributionItem(BaseModel):
    """Status distribution item."""

    status: str
    count: int


class StatusDistributionResponse(BaseModel):
    """Status distribution."""

    items: list[StatusDistributionItem]


# ============================================================================
# Admin Run Management Responses
# ============================================================================


class AdminRunSummary(BaseModel):
    """Run summary for admin view with user info."""

    id: str
    user_id: str
    user_email: str | None = None
    status: str
    created_at: datetime
    csv_filename: str
    target_variable: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    analysis_type: str = "quick"
    start_time: datetime | None = None
    finish_time: datetime | None = None
    error: str | None = None

    class Config:
        from_attributes = True


class PaginatedAdminRunsResponse(BaseModel):
    """Paginated list of runs for admin."""

    items: list[AdminRunSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class AdminRunDetailResponse(BaseModel):
    """Detailed run info for admin view."""

    id: str
    user_id: str
    user_email: str | None = None
    status: str
    created_at: datetime | None = None
    problem_description: dict[str, Any]
    csv_filename: str
    analysis_type: str = "quick"
    error: str | None = None
    progress: int = 0
    start_time: datetime | None = None
    finish_time: datetime | None = None
    results: dict[str, Any] | None = None
    slurm_job_ids: dict[str, Any] | None = None


class AdminRunActionResponse(BaseModel):
    """Response for admin run actions."""

    success: bool
    message: str
    run_id: str


# ============================================================================
# System Monitoring Responses
# ============================================================================


class SystemHealthResponse(BaseModel):
    """System health status."""

    database_connected: bool
    slurm_configured: bool
    slurm_connected: bool
    api_healthy: bool
    uptime_seconds: int
    checked_at: str


class PartitionInfo(BaseModel):
    """Slurm partition info."""

    name: str
    state: str
    total_nodes: int
    total_cpus: int


class SlurmStatusResponse(BaseModel):
    """Slurm cluster status."""

    cluster_status: str
    queue_length: int
    active_jobs: int
    total_jobs: int
    partitions: list[PartitionInfo]
    node_status: dict[str, int]
    total_nodes: int
    checked_at: str
    error: str | None = None
    # Configuration info for highlighting in UI
    configured_partition: str | None = None
    configured_cpus: int | None = None
    configured_memory: str | None = None


# ============================================================================
# Audit Log Responses
# ============================================================================


class AuditLogEntry(BaseModel):
    """Single audit log entry."""

    id: str
    admin_email: str
    action: str
    target_type: str
    target_id: str
    details: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedAuditLogsResponse(BaseModel):
    """Paginated audit logs."""

    items: list[AuditLogEntry]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class AuditFilterOptionsResponse(BaseModel):
    """Available audit log filter options."""

    actions: list[str]
    admins: list[str]


# ============================================================================
# Error Monitoring Responses
# ============================================================================


class ErrorDistributionItem(BaseModel):
    """Error type distribution item."""

    error_type: str
    count: int


class ErrorDistributionResponse(BaseModel):
    """Error distribution."""

    items: list[ErrorDistributionItem]


class ErrorTrendItem(BaseModel):
    """Daily error trend item."""

    date: str
    total: int
    failed: int
    failure_rate: float


class ErrorTrendResponse(BaseModel):
    """Error trend over time."""

    items: list[ErrorTrendItem]


# ============================================================================
# Analytics Responses
# ============================================================================


class UserGrowthItem(BaseModel):
    """Daily user growth item."""

    date: str
    count: int


class UserGrowthResponse(BaseModel):
    """User growth trend."""

    items: list[UserGrowthItem]


class TopUserItem(BaseModel):
    """Top user by activity."""

    user_id: str
    email: str | None = None
    run_count: int
    completed: int


class TopUsersResponse(BaseModel):
    """Top users list."""

    items: list[TopUserItem]


class PerformanceStatsResponse(BaseModel):
    """Performance analytics."""

    avg_duration: float
    median_duration: float
    p95_duration: float
    success_rate: float
    total_completed: int


class PerformanceByTypeItem(BaseModel):
    """Performance by analysis type."""

    type: str
    total_runs: int
    completed: int
    failed: int
    avg_duration: float
    success_rate: float


class PerformanceByTypeResponse(BaseModel):
    """Performance by type."""

    items: list[PerformanceByTypeItem]


# ============================================================================
# Configuration Response
# ============================================================================


class RateLimitsConfig(BaseModel):
    """Rate limit configuration."""

    runs_per_minute: int
    uploads_per_minute: int
    admin_requests_per_minute: int


class FeaturesConfig(BaseModel):
    """Feature flags."""

    slurm_configured: bool
    literature_search_enabled: bool
    user_api_keys_enabled: bool


class SecretsConfig(BaseModel):
    """Masked secrets configuration."""

    openai_api_key: str | None = None
    slurm_auth_token: str | None = None
    database_host: str | None = None


class ConfigResponse(BaseModel):
    """Sanitized system configuration."""

    compute_backend: str
    analysis_timeout_hours: float
    max_file_size_mb: int
    rate_limits: RateLimitsConfig
    features: FeaturesConfig
    secrets: SecretsConfig


# ============================================================================
# Activity Feed
# ============================================================================


class ActivityItem(BaseModel):
    """Recent activity item."""

    id: str
    admin_email: str
    action: str
    target_type: str
    target_id: str
    details: dict[str, Any] | None = None
    created_at: datetime


class RecentActivityResponse(BaseModel):
    """Recent activity feed."""

    items: list[ActivityItem]


# ============================================================================
# Feedback Responses
# ============================================================================


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    success: bool
    issue_url: str | None = None
    issue_number: int | None = None
    message: str
