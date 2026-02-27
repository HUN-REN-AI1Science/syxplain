"""
Syxplain API - Main Application Entry Point

This is a minimal entry point that configures the FastAPI application,
registers middleware, and includes all routers. Business logic has been
moved to the service layer for cleaner separation of concerns.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from backend.api.routers import (
    admin,
    api_keys,
    config,
    feedback,
    files,
    permissions,
    profile,
    programmatic,
    progress,
    runs,
    sharing,
)
from backend.api.sse.progress_sse import router as progress_sse_router
from backend.core.config import get_settings
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import configure_logging, configure_uvicorn_logging
from backend.core.rate_limit import limiter
from backend.core.security_logging import SecurityLoggingMiddleware
from backend.infrastructure.database.connection import init_db

# ============================================================================
# Logging Configuration (must be first)
# ============================================================================

configure_logging()
logger = logging.getLogger(__name__)


# ============================================================================
# Security Middleware
# ============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Prevent caching of sensitive data
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        # Content Security Policy (skip for interactive docs which load external JS/CSS)
        if not request.url.path.startswith(("/docs", "/openapi.json")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; frame-ancestors 'none'"
            )
        # Permissions Policy
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


# ============================================================================
# Application Factory
# ============================================================================


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    tags_metadata = [
        {
            "name": "Programmatic API (v1)",
            "description": "Script-friendly endpoints for automated analysis. "
            "Authenticate with `X-API-Key` header. "
            "Upload + analyze in one call, poll for results.",
        },
    ]

    app = FastAPI(
        title="Syxplain API",
        description=(
            "**Syxplain** -- Neurosymbolic Scientific Discovery Platform\n\n"
            "Automated symbolic regression + LLM explanation for scientific data.\n\n"
            "## Authentication\n\n"
            "All endpoints require an API key passed via the `X-API-Key` header.\n\n"
            "Generate an API key in the web UI (Profile -> API Keys).\n\n"
            "## API Specification\n\n"
            "- **OpenAPI JSON:** [`/openapi.json`](/openapi.json) (download for code generation)"
        ),
        version="1.0.0",
        redoc_url=None,
        openapi_tags=tags_metadata,
    )

    # Override OpenAPI schema to remove internal auth schemes (HTTPBearer)
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            tags=tags_metadata,
        )
        # Remove HTTPBearer scheme — only X-API-Key is relevant for public docs
        components = schema.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        security_schemes.pop("HTTPBearer", None)
        # Remove Bearer security requirement from all endpoints
        for path_methods in schema.get("paths", {}).values():
            for operation in path_methods.values():
                if isinstance(operation, dict) and "security" in operation:
                    operation["security"] = [
                        s for s in operation["security"] if "HTTPBearer" not in s
                    ]
                    if not operation["security"]:
                        del operation["security"]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi

    # -------------------------------------------------------------------------
    # Middleware Configuration (order matters - first added = last executed)
    # -------------------------------------------------------------------------

    # Rate limiting (OWASP: A04 - Security Misconfiguration prevention)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Security logging (OWASP: A09 - Security Logging and Monitoring)
    app.add_middleware(SecurityLoggingMiddleware)

    # Security headers (OWASP best practices)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS configuration
    # SECURITY: Never use allow_credentials=True with allow_origins=["*"]
    allowed_origins = settings.cors.get_allowed_origins()
    is_wildcard = allowed_origins == ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=not is_wildcard,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-API-Key"],
        expose_headers=["Content-Disposition"],
    )

    # -------------------------------------------------------------------------
    # Exception Handlers
    # -------------------------------------------------------------------------

    register_exception_handlers(app)

    # -------------------------------------------------------------------------
    # Health Check Endpoint
    # -------------------------------------------------------------------------

    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check():
        """Health check endpoint for load balancers and container orchestration."""
        return {"status": "healthy"}

    # -------------------------------------------------------------------------
    # Router Registration (order matters for path matching)
    # -------------------------------------------------------------------------

    # Public API (visible in /docs)
    app.include_router(programmatic.router)  # /api/v1/ — programmatic API

    # Internal routers (hidden from OpenAPI docs, JWT-only auth)
    app.include_router(api_keys.router, include_in_schema=False)
    app.include_router(admin.router, include_in_schema=False)
    app.include_router(config.router, include_in_schema=False)
    app.include_router(feedback.router, include_in_schema=False)
    app.include_router(files.router, include_in_schema=False)
    app.include_router(permissions.router, include_in_schema=False)
    app.include_router(profile.router, include_in_schema=False)
    app.include_router(progress.router, include_in_schema=False)
    app.include_router(progress_sse_router, include_in_schema=False)  # SSE
    app.include_router(sharing.router, include_in_schema=False)  # Before runs
    app.include_router(runs.router, include_in_schema=False)

    # -------------------------------------------------------------------------
    # Lifecycle Events
    # -------------------------------------------------------------------------

    @app.on_event("startup")
    async def on_startup():
        """Initialize database."""
        logger.info("Starting Syxplain API...")

        # Configure uvicorn access log filtering
        configure_uvicorn_logging()

        # Initialize database and run migrations
        init_db()

        logger.info("Syxplain API started successfully")

    return app


# ============================================================================
# Application Instance
# ============================================================================

app = create_app()


# ============================================================================
# Development Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
