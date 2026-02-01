"""
Admin endpoints router.

Provides endpoints for administrative user management, monitoring,
and analytics.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.dependencies import (
    get_permission_service,
    get_audit_service,
    get_admin_stats_service,
    get_system_monitor_service,
    get_run_repository,
)
from backend.core.rate_limit import limiter
from backend.core.config import get_settings
from backend.core.security import User, get_current_user
from backend.services.permission_service import PermissionService
from backend.services.audit_service import AuditService
from backend.services.admin_stats_service import AdminStatsService
from backend.services.system_monitor_service import SystemMonitorService
from backend.repositories.run_repository import RunRepository, AdminRunFilters, PaginationParams
from backend.schemas.requests import UpdatePermissionRequest
from backend.schemas.responses import (
    # User management
    UsersWithPermissionsResponse,
    UserPermissionInfo,
    UpdatePermissionResponse,
    # Dashboard
    DashboardStatsResponse,
    RunTrendsResponse,
    RunTrendItem,
    StatusDistributionResponse,
    StatusDistributionItem,
    # Run management
    PaginatedAdminRunsResponse,
    AdminRunSummary,
    AdminRunDetailResponse,
    AdminRunActionResponse,
    # System monitoring
    SystemHealthResponse,
    SlurmStatusResponse,
    PartitionInfo,
    # Audit logs
    PaginatedAuditLogsResponse,
    AuditLogEntry,
    AuditFilterOptionsResponse,
    # Error monitoring
    ErrorDistributionResponse,
    ErrorDistributionItem,
    ErrorTrendResponse,
    ErrorTrendItem,
    # Analytics
    UserGrowthResponse,
    UserGrowthItem,
    TopUsersResponse,
    TopUserItem,
    PerformanceStatsResponse,
    PerformanceByTypeResponse,
    PerformanceByTypeItem,
    # Config
    ConfigResponse,
    RateLimitsConfig,
    FeaturesConfig,
    SecretsConfig,
    # Activity
    RecentActivityResponse,
    ActivityItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency that requires admin access.

    Raises:
        HTTPException: If user is not an admin
    """
    settings = get_settings()
    if not settings.admin.is_admin(current_user.email):
        logger.warning(f"Non-admin user {current_user.email} attempted admin access")
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ============================================================================
# User Management Endpoints
# ============================================================================

@router.get(
    "/users",
    response_model=UsersWithPermissionsResponse
)
@limiter.limit("30/minute")
def list_users_with_permissions(
    request: Request,
    admin: User = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    List all users with their permissions.

    Returns:
        UsersWithPermissionsResponse with list of users and their permission status
    """
    users = permission_service.list_users_with_permissions()
    return UsersWithPermissionsResponse(
        users=[
            UserPermissionInfo(
                user_id=u["user_id"],
                email=u["email"],
                use_hunren_keys=u["use_hunren_keys"],
                granted_by=u["granted_by"],
                user_created_at=u["user_created_at"],
                permission_updated_at=u["permission_updated_at"]
            )
            for u in users
        ]
    )


@router.put(
    "/users/{user_id}/permissions",
    response_model=UpdatePermissionResponse
)
@limiter.limit("20/minute")
def update_user_permission(
    request: Request,
    user_id: str,
    body: UpdatePermissionRequest,
    admin: User = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service),
    audit_service: AuditService = Depends(get_audit_service),
):
    """
    Grant or revoke HUN-REN key permission for a user.

    Args:
        user_id: The target user's UUID
        request: Permission update request

    Returns:
        UpdatePermissionResponse with success status
    """
    from backend.utils import parse_uuid
    try:
        parse_uuid(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    permission_service.set_permission(
        user_id=user_id,
        use_hunren_keys=body.use_hunren_keys,
        granted_by=admin.email
    )

    action = "grant_permission" if body.use_hunren_keys else "revoke_permission"
    audit_service.log_action(
        admin_email=admin.email,
        action=action,
        target_type="user",
        target_id=user_id,
        details={"use_hunren_keys": body.use_hunren_keys},
        ip_address=get_client_ip(request),
    )

    logger.info(f"Admin {admin.email} {action} for user {user_id}")

    return UpdatePermissionResponse(
        success=True,
        user_id=user_id,
        use_hunren_keys=body.use_hunren_keys
    )


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@router.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse
)
@limiter.limit("60/minute")
def get_dashboard_stats(
    request: Request,
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get dashboard statistics."""
    stats = stats_service.get_dashboard_stats()
    return DashboardStatsResponse(**stats)


@router.get(
    "/dashboard/trends",
    response_model=RunTrendsResponse
)
@limiter.limit("30/minute")
def get_run_trends(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get daily run trends."""
    trends = stats_service.get_run_trends(days=days)
    return RunTrendsResponse(items=[RunTrendItem(**t) for t in trends])


@router.get(
    "/dashboard/status-distribution",
    response_model=StatusDistributionResponse
)
@limiter.limit("30/minute")
def get_status_distribution(
    request: Request,
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get current run status distribution."""
    distribution = stats_service.get_status_distribution()
    return StatusDistributionResponse(items=[StatusDistributionItem(**d) for d in distribution])


@router.get(
    "/dashboard/recent-activity",
    response_model=RecentActivityResponse
)
@limiter.limit("60/minute")
def get_recent_activity(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    admin: User = Depends(require_admin),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Get recent admin activity."""
    activity = audit_service.get_recent_activity(limit=limit)
    return RecentActivityResponse(items=[ActivityItem(**a) for a in activity])


# ============================================================================
# Run Management Endpoints
# ============================================================================

@router.get(
    "/runs",
    response_model=PaginatedAdminRunsResponse
)
@limiter.limit("30/minute")
def get_all_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    sort_field: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    status: Optional[str] = None,
    analysis_type: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    admin: User = Depends(require_admin),
    run_repo: RunRepository = Depends(get_run_repository),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all runs across all users with filtering."""
    filters = AdminRunFilters(
        status=status,
        analysis_type=analysis_type,
        user_id=user_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    pagination = PaginationParams(
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_order=sort_order,
    )

    result = run_repo.get_all_runs(filters=filters, pagination=pagination)

    # Get user emails for all runs
    users = permission_service.list_users_with_permissions()
    user_emails = {u["user_id"]: u["email"] for u in users}

    return PaginatedAdminRunsResponse(
        items=[
            AdminRunSummary(
                id=str(run.id),
                user_id=str(run.user_id),
                user_email=user_emails.get(str(run.user_id)),
                status=run.status,
                created_at=run.created_at,
                csv_filename=run.csv_filename,
                target_variable=run.target_variable,
                progress=run.progress,
                analysis_type=run.analysis_type,
                start_time=run.start_time,
                finish_time=run.finish_time,
                error=run.error,
            )
            for run in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get(
    "/runs/{run_id}",
    response_model=AdminRunDetailResponse
)
@limiter.limit("30/minute")
def get_run_detail(
    request: Request,
    run_id: str,
    admin: User = Depends(require_admin),
    run_repo: RunRepository = Depends(get_run_repository),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get detailed run information."""
    from backend.utils import parse_uuid
    try:
        run_uuid = parse_uuid(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID format")

    run = run_repo.admin_get_run(run_uuid)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get user email
    users = permission_service.list_users_with_permissions()
    user_emails = {u["user_id"]: u["email"] for u in users}

    return AdminRunDetailResponse(
        id=str(run.id),
        user_id=str(run.user_id),
        user_email=user_emails.get(str(run.user_id)),
        status=run.status,
        created_at=run.created_at,
        problem_description=run.problem_description,
        csv_filename=run.csv_filename,
        analysis_type=run.analysis_type,
        error=run.error,
        progress=run.progress,
        start_time=run.start_time,
        finish_time=run.finish_time,
        results=run.results,
        slurm_job_ids=run.slurm_job_ids,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=AdminRunActionResponse
)
@limiter.limit("20/minute")
def cancel_run(
    request: Request,
    run_id: str,
    admin: User = Depends(require_admin),
    run_repo: RunRepository = Depends(get_run_repository),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Cancel a run."""
    from backend.utils import parse_uuid
    try:
        run_uuid = parse_uuid(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID format")

    run = run_repo.admin_cancel_run(run_uuid)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    audit_service.log_action(
        admin_email=admin.email,
        action="cancel_run",
        target_type="run",
        target_id=run_id,
        details={"previous_status": run.status},
        ip_address=get_client_ip(request),
    )

    return AdminRunActionResponse(
        success=True,
        message="Run cancelled successfully",
        run_id=run_id,
    )


@router.delete(
    "/runs/{run_id}",
    response_model=AdminRunActionResponse
)
@limiter.limit("10/minute")
def delete_run(
    request: Request,
    run_id: str,
    admin: User = Depends(require_admin),
    run_repo: RunRepository = Depends(get_run_repository),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Delete a run and all associated data."""
    from backend.utils import parse_uuid
    try:
        run_uuid = parse_uuid(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run ID format")

    # Get run details for audit log before deletion
    run = run_repo.admin_get_run(run_uuid)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    deleted = run_repo.admin_delete_run(run_uuid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")

    audit_service.log_action(
        admin_email=admin.email,
        action="delete_run",
        target_type="run",
        target_id=run_id,
        details={
            "user_id": str(run.user_id),
            "csv_filename": run.csv_filename,
            "status": run.status,
        },
        ip_address=get_client_ip(request),
    )

    return AdminRunActionResponse(
        success=True,
        message="Run deleted successfully",
        run_id=run_id,
    )


# ============================================================================
# System Monitoring Endpoints
# ============================================================================

@router.get(
    "/system/health",
    response_model=SystemHealthResponse
)
@limiter.limit("60/minute")
def get_system_health(
    request: Request,
    admin: User = Depends(require_admin),
    monitor_service: SystemMonitorService = Depends(get_system_monitor_service),
):
    """Get system health status."""
    health = monitor_service.get_health_status()
    return SystemHealthResponse(**health)


@router.get(
    "/system/slurm",
    response_model=SlurmStatusResponse
)
@limiter.limit("30/minute")
def get_slurm_status(
    request: Request,
    admin: User = Depends(require_admin),
    monitor_service: SystemMonitorService = Depends(get_system_monitor_service),
):
    """Get Slurm cluster status."""
    status = monitor_service.get_slurm_status()
    if status is None:
        raise HTTPException(status_code=404, detail="Slurm not enabled")

    if "error" in status and not status.get("cluster_status"):
        raise HTTPException(status_code=503, detail=status.get("error", "Slurm unavailable"))

    # Convert partition dicts to PartitionInfo models
    partitions = [
        PartitionInfo(**p) for p in status.get("partitions", [])
    ]

    return SlurmStatusResponse(
        cluster_status=status.get("cluster_status", "unknown"),
        queue_length=status.get("queue_length", 0),
        active_jobs=status.get("active_jobs", 0),
        total_jobs=status.get("total_jobs", 0),
        partitions=partitions,
        node_status=status.get("node_status", {}),
        total_nodes=status.get("total_nodes", 0),
        checked_at=status.get("checked_at", datetime.utcnow().isoformat()),
        error=status.get("error"),
    )


# ============================================================================
# Error Monitoring Endpoints
# ============================================================================

@router.get(
    "/errors/runs",
    response_model=PaginatedAdminRunsResponse
)
@limiter.limit("30/minute")
def get_failed_runs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    days: int = Query(default=30, ge=1, le=365),
    admin: User = Depends(require_admin),
    run_repo: RunRepository = Depends(get_run_repository),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get failed and timeout runs."""
    result = run_repo.get_failed_runs(days=days, page=page, page_size=page_size)

    # Get user emails
    users = permission_service.list_users_with_permissions()
    user_emails = {u["user_id"]: u["email"] for u in users}

    return PaginatedAdminRunsResponse(
        items=[
            AdminRunSummary(
                id=str(run.id),
                user_id=str(run.user_id),
                user_email=user_emails.get(str(run.user_id)),
                status=run.status,
                created_at=run.created_at,
                csv_filename=run.csv_filename,
                target_variable=run.target_variable,
                progress=run.progress,
                analysis_type=run.analysis_type,
                start_time=run.start_time,
                finish_time=run.finish_time,
                error=run.error,
            )
            for run in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get(
    "/errors/distribution",
    response_model=ErrorDistributionResponse
)
@limiter.limit("30/minute")
def get_error_distribution(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get error type distribution."""
    distribution = stats_service.get_error_distribution(days=days)
    return ErrorDistributionResponse(
        items=[ErrorDistributionItem(**d) for d in distribution]
    )


@router.get(
    "/errors/trend",
    response_model=ErrorTrendResponse
)
@limiter.limit("30/minute")
def get_error_trend(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get daily error trend."""
    trend = stats_service.get_error_trend(days=days)
    return ErrorTrendResponse(items=[ErrorTrendItem(**t) for t in trend])


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get(
    "/audit-logs",
    response_model=PaginatedAuditLogsResponse
)
@limiter.limit("30/minute")
def get_audit_logs(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    action: Optional[str] = None,
    admin_email: Optional[str] = None,
    target_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    admin: User = Depends(require_admin),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Get paginated audit logs with filtering."""
    result = audit_service.get_audit_logs(
        page=page,
        page_size=page_size,
        action=action,
        admin_email=admin_email,
        target_type=target_type,
        date_from=date_from,
        date_to=date_to,
    )

    return PaginatedAuditLogsResponse(
        items=[
            AuditLogEntry(
                id=str(log.id),
                admin_email=log.admin_email,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                details=log.details,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get(
    "/audit-logs/filters",
    response_model=AuditFilterOptionsResponse
)
@limiter.limit("30/minute")
def get_audit_filter_options(
    request: Request,
    admin: User = Depends(require_admin),
    audit_service: AuditService = Depends(get_audit_service),
):
    """Get available filter options for audit logs."""
    options = audit_service.get_filter_options()
    return AuditFilterOptionsResponse(**options)


# ============================================================================
# Analytics Endpoints
# ============================================================================

@router.get(
    "/analytics/users/growth",
    response_model=UserGrowthResponse
)
@limiter.limit("30/minute")
def get_user_growth(
    request: Request,
    days: int = Query(default=90, ge=1, le=365),
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get user growth trend."""
    growth = stats_service.get_user_growth(days=days)
    return UserGrowthResponse(items=[UserGrowthItem(**g) for g in growth])


@router.get(
    "/analytics/users/top",
    response_model=TopUsersResponse
)
@limiter.limit("30/minute")
def get_top_users(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    period_days: int = Query(default=30, ge=1, le=365),
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get top users by run count."""
    top_users = stats_service.get_top_users(limit=limit, period_days=period_days)

    # Get user emails
    users = permission_service.list_users_with_permissions()
    user_emails = {u["user_id"]: u["email"] for u in users}

    return TopUsersResponse(
        items=[
            TopUserItem(
                user_id=u["user_id"],
                email=user_emails.get(u["user_id"]),
                run_count=u["run_count"],
                completed=u["completed"],
            )
            for u in top_users
        ]
    )


@router.get(
    "/analytics/performance",
    response_model=PerformanceStatsResponse
)
@limiter.limit("30/minute")
def get_performance_stats(
    request: Request,
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get overall performance analytics."""
    stats = stats_service.get_performance_stats()
    return PerformanceStatsResponse(**stats)


@router.get(
    "/analytics/performance/by-type",
    response_model=PerformanceByTypeResponse
)
@limiter.limit("30/minute")
def get_performance_by_type(
    request: Request,
    admin: User = Depends(require_admin),
    stats_service: AdminStatsService = Depends(get_admin_stats_service),
):
    """Get performance metrics by analysis type."""
    by_type = stats_service.get_performance_by_type()
    return PerformanceByTypeResponse(
        items=[PerformanceByTypeItem(**t) for t in by_type]
    )


# ============================================================================
# Configuration Endpoint
# ============================================================================

@router.get(
    "/config",
    response_model=ConfigResponse
)
@limiter.limit("30/minute")
def get_config(
    request: Request,
    admin: User = Depends(require_admin),
    monitor_service: SystemMonitorService = Depends(get_system_monitor_service),
):
    """Get sanitized system configuration."""
    config = monitor_service.get_config_summary()

    return ConfigResponse(
        compute_backend=config["compute_backend"],
        analysis_timeout_hours=config["analysis_timeout_hours"],
        max_file_size_mb=config["max_file_size_mb"],
        rate_limits=RateLimitsConfig(**config["rate_limits"]),
        features=FeaturesConfig(**config["features"]),
        secrets=SecretsConfig(**config["secrets"]),
    )
