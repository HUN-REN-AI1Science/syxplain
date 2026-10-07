# Core Module
# Re-export for convenient imports

from backend.core.config import (
    AnalysisSettings,
    AuthSettings,
    CORSSettings,
    DatabaseSettings,
    DiscoverySettings,
    LLMSettings,
    Settings,
    get_auth_settings,
    get_settings,
)
from backend.core.exceptions import (
    AnalysisError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    EntityNotFoundError,
    ExternalServiceError,
    FileTooLargeError,
    FileValidationError,
    SyxplainException,
    ValidationError,
    register_exception_handlers,
)
from backend.core.logging import (
    configure_debug_mode,
    configure_logging,
    configure_uvicorn_logging,
    get_logger,
)
from backend.core.security import (
    User,
    get_current_user,
    get_optional_user,
    verify_user_owns_resource,
)

__all__ = [
    "AnalysisError",
    "AnalysisSettings",
    "AuthSettings",
    "AuthenticationError",
    "AuthorizationError",
    "CORSSettings",
    "ConfigurationError",
    "DatabaseSettings",
    "DiscoverySettings",
    "EntityNotFoundError",
    "ExternalServiceError",
    "FileTooLargeError",
    "FileValidationError",
    "LLMSettings",
    "Settings",
    # Exceptions
    "SyxplainException",
    # Security
    "User",
    "ValidationError",
    "configure_debug_mode",
    # Logging
    "configure_logging",
    "configure_uvicorn_logging",
    "get_auth_settings",
    "get_current_user",
    "get_logger",
    "get_optional_user",
    # Config
    "get_settings",
    "register_exception_handlers",
    "verify_user_owns_resource",
]
