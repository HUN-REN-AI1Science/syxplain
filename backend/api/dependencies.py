"""
FastAPI dependency injection configuration.

Provides factory functions for injecting repositories and services
into route handlers, enabling loose coupling and testability.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.infrastructure.database.connection import get_db
from backend.repositories.api_key_repository import ApiKeyRepository
from backend.repositories.artifact_repository import ArtifactRepository
from backend.repositories.audit_repository import AuditRepository
from backend.repositories.file_repository import FileRepository
from backend.repositories.run_repository import RunRepository
from backend.services.admin_stats_service import AdminStatsService
from backend.services.api_key_service import ApiKeyService
from backend.services.audit_service import AuditService
from backend.services.file_service import FileService, get_file_service
from backend.services.permission_service import PermissionService
from backend.services.profile_service import ProfileService
from backend.services.run_service import RunService
from backend.services.share_service import ShareService
from backend.services.system_monitor_service import SystemMonitorService

# ============================================================================
# Repository Dependencies
# ============================================================================


def get_run_repository(db: Session = Depends(get_db)) -> RunRepository:
    """Provide RunRepository instance."""
    return RunRepository(db)


def get_file_repository(db: Session = Depends(get_db)) -> FileRepository:
    """Provide FileRepository instance."""
    return FileRepository(db)


def get_artifact_repository(db: Session = Depends(get_db)) -> ArtifactRepository:
    """Provide ArtifactRepository instance."""
    return ArtifactRepository(db)


def get_api_key_repository(db: Session = Depends(get_db)) -> ApiKeyRepository:
    """Provide ApiKeyRepository instance."""
    return ApiKeyRepository(db)


# ============================================================================
# Service Dependencies
# ============================================================================


def get_file_service_dep() -> FileService:
    """Provide FileService instance."""
    return get_file_service()


def get_run_service(
    run_repo: RunRepository = Depends(get_run_repository),
    file_repo: FileRepository = Depends(get_file_repository),
    artifact_repo: ArtifactRepository = Depends(get_artifact_repository),
    file_service: FileService = Depends(get_file_service_dep),
) -> RunService:
    """
    Provide RunService instance with all dependencies.

    Dependencies are automatically injected by FastAPI's
    dependency injection system.
    """
    return RunService(
        run_repo=run_repo,
        file_repo=file_repo,
        artifact_repo=artifact_repo,
        file_service=file_service,
    )


def get_share_service(
    run_repo: RunRepository = Depends(get_run_repository),
    file_repo: FileRepository = Depends(get_file_repository),
    file_service: FileService = Depends(get_file_service_dep),
    artifact_repo: ArtifactRepository = Depends(get_artifact_repository),
) -> ShareService:
    """Provide ShareService instance with all dependencies."""
    return ShareService(
        run_repo=run_repo,
        file_repo=file_repo,
        file_service=file_service,
        artifact_repo=artifact_repo,
    )


def get_profile_service(
    run_repo: RunRepository = Depends(get_run_repository),
    file_repo: FileRepository = Depends(get_file_repository),
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
) -> ProfileService:
    """Provide ProfileService instance with all dependencies."""
    return ProfileService(run_repo=run_repo, file_repo=file_repo, api_key_repo=api_key_repo)


def get_api_key_service(
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
) -> ApiKeyService:
    """Provide ApiKeyService instance."""
    return ApiKeyService(api_key_repo=api_key_repo)


def get_permission_service() -> PermissionService:
    """Provide PermissionService instance."""
    return PermissionService()


# ============================================================================
# Admin Dependencies
# ============================================================================


def get_audit_repository(db: Session = Depends(get_db)) -> AuditRepository:
    """Provide AuditRepository instance."""
    return AuditRepository(db)


def get_audit_service(audit_repo: AuditRepository = Depends(get_audit_repository)) -> AuditService:
    """Provide AuditService instance."""
    return AuditService(audit_repo=audit_repo)


def get_admin_stats_service(db: Session = Depends(get_db)) -> AdminStatsService:
    """Provide AdminStatsService instance."""
    return AdminStatsService(db=db)


def get_system_monitor_service(db: Session = Depends(get_db)) -> SystemMonitorService:
    """Provide SystemMonitorService instance."""
    return SystemMonitorService(db=db)
