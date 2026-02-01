# Core Module
# Re-export for convenient imports

from backend.core.config import (
    get_settings,
    get_auth_settings,
    Settings,
    DatabaseSettings,
    AuthSettings,
    LLMSettings,
    CORSSettings,
    AnalysisSettings,
    SHAPSettings,
)
from backend.core.exceptions import (
    SyxplainException,
    EntityNotFoundError,
    AuthorizationError,
    AuthenticationError,
    ValidationError,
    FileValidationError,
    FileTooLargeError,
    ExternalServiceError,
    AnalysisError,
    ConfigurationError,
    register_exception_handlers,
)
from backend.core.security import (
    User,
    get_current_user,
    get_optional_user,
    verify_user_owns_resource,
)
from backend.core.logging import (
    configure_logging,
    configure_debug_mode,
    configure_uvicorn_logging,
    get_logger,
)

__all__ = [
    # Config
    "get_settings",
    "get_auth_settings",
    "Settings",
    "DatabaseSettings",
    "AuthSettings",
    "LLMSettings",
    "CORSSettings",
    "AnalysisSettings",
    "SHAPSettings",
    # Exceptions
    "SyxplainException",
    "EntityNotFoundError",
    "AuthorizationError",
    "AuthenticationError",
    "ValidationError",
    "FileValidationError",
    "FileTooLargeError",
    "ExternalServiceError",
    "AnalysisError",
    "ConfigurationError",
    "register_exception_handlers",
    # Security
    "User",
    "get_current_user",
    "get_optional_user",
    "verify_user_owns_resource",
    # Logging
    "configure_logging",
    "configure_debug_mode",
    "configure_uvicorn_logging",
    "get_logger",
]
