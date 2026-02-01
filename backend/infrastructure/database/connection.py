"""
Database connection management.

Provides SQLAlchemy engine and session factory with proper
connection pooling configuration.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import get_settings, DatabaseSettings

logger = logging.getLogger(__name__)

# Global engine and session factory - initialized lazily
_engine: Engine = None
_SessionLocal: sessionmaker = None


def get_engine(settings: DatabaseSettings = None) -> Engine:
    """
    Get or create the SQLAlchemy engine.

    Uses lazy initialization to allow configuration to be loaded first.

    Args:
        settings: Optional database settings, uses defaults if not provided

    Returns:
        Configured SQLAlchemy engine
    """
    global _engine

    if _engine is None:
        if settings is None:
            settings = get_settings().database

        _engine = create_engine(
            settings.url,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_pre_ping=True,
            pool_recycle=settings.pool_recycle,
            pool_timeout=settings.pool_timeout
        )
        logger.info(f"Database engine created with pool_size={settings.pool_size}")

    return _engine


def get_session_factory() -> sessionmaker:
    """
    Get or create the session factory.

    Returns:
        Configured sessionmaker bound to the engine
    """
    global _SessionLocal

    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields a session and ensures it's closed after the request,
    even if an exception occurs.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for getting a database session outside of FastAPI.

    Useful for background workers and scripts.

    Usage:
        with get_db_session() as db:
            run = db.query(Run).get(run_id)
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def dispose_engine() -> None:
    """
    Dispose of all connections in the pool.

    Should be called when forking processes to ensure
    child processes don't share connections with parent.
    """
    global _engine
    if _engine is not None:
        _engine.dispose()
        logger.info("Database engine connections disposed")


def init_db() -> None:
    """
    Run Alembic migrations to ensure database schema is up to date.

    Simply checks alembic_version table and applies any pending migrations.
    """
    import os
    from alembic.config import Config
    from alembic import command
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext

    settings = get_settings().database
    engine = get_engine()

    try:
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
        alembic_cfg.set_main_option(
            "script_location",
            os.path.join(os.path.dirname(__file__), "..", "..", "alembic")
        )
        alembic_cfg.set_main_option("sqlalchemy.url", settings.url)

        # Get current revision and head revision for logging
        script = ScriptDirectory.from_config(alembic_cfg)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()

        head_rev = script.get_current_head()

        if current_rev == head_rev:
            logger.info(f"Database schema is up to date (revision: {current_rev})")
        else:
            logger.info(f"Running database migrations from {current_rev} to {head_rev}...")
            command.upgrade(alembic_cfg, "head")
            logger.info(f"Database migrations completed successfully. Now at revision: {head_rev}")

    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        logger.exception("Full migration error traceback:")
        raise


