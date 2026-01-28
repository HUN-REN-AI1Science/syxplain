"""
Syxplain API - Main Application Entry Point

This is a minimal entry point that configures the FastAPI application,
registers middleware, and includes all routers. Business logic has been
moved to the service layer for cleaner separation of concerns.
"""
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import configure_logging, configure_uvicorn_logging
from backend.infrastructure.database.connection import init_db
from backend.workers.analysis_worker import cleanup_processes, check_timed_out_runs

# Import routers
from backend.api.routers import config, files, profile, progress, runs, sharing

# Configure logging FIRST
configure_logging()
logger = logging.getLogger(__name__)


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

    # Health check endpoint (for container orchestration)
    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancers and container orchestration."""
        return {"status": "healthy"}

    # Register routers (Order matters! Specific paths before parameterized ones)
    app.include_router(config.router)
    app.include_router(files.router)
    app.include_router(profile.router)
    app.include_router(progress.router)  # Internal progress webhook for Slurm workers
    app.include_router(sharing.router)  # Sharing before Runs to capture /api/runs/shared
    app.include_router(runs.router)

    # Register lifecycle events
    @app.on_event("startup")
    async def on_startup():
        """Initialize database and start background tasks."""
        logger.info("Starting Syxplain API...")

        # Apply uvicorn access log filtering
        configure_uvicorn_logging()

        # Initialize database
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
        logger.info("Syxplain API started successfully")

    return app


# Create application instance
app = create_app()


# ============================================================================
# Development Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
