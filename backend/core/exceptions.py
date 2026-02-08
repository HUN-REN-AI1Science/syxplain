"""
Custom exception hierarchy for the Syxplain backend.

Provides structured exceptions that map to appropriate HTTP status codes
and include detailed error information for logging and debugging.
"""

from typing import Any


class SyxplainException(Exception):
    """
    Base exception for all Syxplain-specific errors.

    Attributes:
        message: Human-readable error description
        details: Additional context for debugging
        status_code: HTTP status code to return
    """

    status_code: int = 500

    def __init__(
        self, message: str, details: dict[str, Any] | None = None, status_code: int | None = None
    ):
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API response."""
        return {"error": self.__class__.__name__, "message": self.message, "details": self.details}


class EntityNotFoundError(SyxplainException):
    """
    Raised when a requested entity does not exist.

    Maps to HTTP 404 Not Found.
    """

    status_code = 404

    def __init__(self, entity_type: str, identifier: Any, message: str | None = None):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(
            message=message or f"{entity_type} not found",
            details={"entity_type": entity_type, "identifier": str(identifier)},
        )


class AuthorizationError(SyxplainException):
    """
    Raised when a user is not authorized to perform an action.

    Maps to HTTP 403 Forbidden.
    """

    status_code = 403

    def __init__(
        self, message: str = "Not authorized to perform this action", resource: str | None = None
    ):
        super().__init__(message=message, details={"resource": resource} if resource else {})


class AuthenticationError(SyxplainException):
    """
    Raised when authentication fails.

    Maps to HTTP 401 Unauthorized.
    """

    status_code = 401

    def __init__(self, message: str = "Authentication required", reason: str | None = None):
        super().__init__(message=message, details={"reason": reason} if reason else {})


class ValidationError(SyxplainException):
    """
    Raised when input validation fails.

    Maps to HTTP 400 Bad Request.
    """

    status_code = 400

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate long values
        super().__init__(message=message, details=details)


class FileValidationError(ValidationError):
    """Raised when file validation fails."""

    def __init__(self, message: str, filename: str | None = None, file_type: str | None = None):
        details = {}
        if filename:
            details["filename"] = filename
        if file_type:
            details["file_type"] = file_type
        super().__init__(message=message)
        self.details.update(details)


class FileTooLargeError(ValidationError):
    """Raised when uploaded file exceeds size limit."""

    status_code = 413

    def __init__(self, filename: str, size_bytes: int, max_size_bytes: int):
        super().__init__(
            message=f"File too large. Maximum size is {max_size_bytes // (1024 * 1024)}MB.",
            field="file",
        )
        self.details.update(
            {"filename": filename, "size_bytes": size_bytes, "max_size_bytes": max_size_bytes}
        )


class ExternalServiceError(SyxplainException):
    """
    Raised when an external service call fails.

    Maps to HTTP 502 Bad Gateway or 503 Service Unavailable.
    """

    status_code = 502

    def __init__(self, service: str, message: str, original_error: Exception | None = None):
        super().__init__(
            message=f"{service} error: {message}",
            details={
                "service": service,
                "original_error": str(original_error) if original_error else None,
            },
        )
        self.service = service
        self.original_error = original_error


class AnalysisError(SyxplainException):
    """Raised when analysis processing fails."""

    status_code = 500

    def __init__(self, run_id: str, message: str, phase: str | None = None):
        super().__init__(
            message=message,
            details={"run_id": run_id, "phase": phase} if phase else {"run_id": run_id},
        )
        self.run_id = run_id
        self.phase = phase


class ConfigurationError(SyxplainException):
    """Raised when required configuration is missing or invalid."""

    status_code = 500

    def __init__(self, message: str, config_key: str | None = None):
        super().__init__(message=message, details={"config_key": config_key} if config_key else {})


# ============================================================================
# FastAPI Exception Handlers
# ============================================================================

from fastapi import Request
from fastapi.responses import JSONResponse


async def syxplain_exception_handler(request: Request, exc: SyxplainException) -> JSONResponse:
    """
    Global exception handler for SyxplainException and its subclasses.

    Converts exceptions to consistent JSON responses with appropriate
    HTTP status codes.
    """
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, **exc.details})


def register_exception_handlers(app):
    """
    Register all custom exception handlers with the FastAPI app.

    Usage:
        from backend.core.exceptions import register_exception_handlers
        register_exception_handlers(app)
    """
    app.add_exception_handler(SyxplainException, syxplain_exception_handler)
