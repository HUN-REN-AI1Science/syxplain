"""
Syxplain API - Main Application Entry Point

This is a minimal entry point that configures the FastAPI application,
registers middleware, and includes all routers. Business logic has been
moved to the service layer for cleaner separation of concerns.
"""
import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.exceptions import register_exception_handlers
from backend.infrastructure.database.connection import init_db
from backend.workers.analysis_worker import cleanup_processes, check_timed_out_runs

# Import routers
from backend.api.routers import config, files, profile, runs, sharing

# Configure logging
from logger import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


# ============================================================================
# Logging Filter
# ============================================================================

class EndpointFilter(logging.Filter):
    """Filter out /api/runs/ polling logs from uvicorn access logger."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("GET /api/runs/") == -1


# Apply filter to uvicorn access logs
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


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

    app = FastAPI(
        title="Syxplain API",
        description="Symbolic Regression Explanation API",
        version="1.0.0"
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    app.include_router(config.router)
    app.include_router(files.router)
    app.include_router(profile.router)
    app.include_router(runs.router)
    app.include_router(sharing.router)

    # Register lifecycle events
    @app.on_event("startup")
    async def on_startup():
        """Initialize database and start background tasks."""
        init_db()

        # Start background task for process cleanup and timeout checking
        async def periodic_cleanup():
            while True:
                try:
                    cleanup_processes()
                    check_timed_out_runs()
                except Exception as e:
                    logger.error(f"Error in process cleanup task: {e}")
                await asyncio.sleep(60)  # Check every minute

        asyncio.create_task(periodic_cleanup())

    return app


# Create application instance
app = create_app()


# ============================================================================
# Development Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
