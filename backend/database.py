from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
import os
import uuid
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://syxplain:syxplain@localhost:5432/syxplain")

engine = create_engine(
    DATABASE_URL,
    pool_size=40,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=30
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class File(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    filename = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    media_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(String, default="pending")  # pending, running, completed, failed
    analysis_type = Column(String, default="quick")  # "quick" or "deep"
    problem_description = Column(JSONB, nullable=False)
    csv_filename = Column(String, nullable=False) # Store filename for reference
    error = Column(Text, nullable=True)
    results = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    steps = relationship("RunStep", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("RunArtifact", back_populates="run", cascade="all, delete-orphan")

class RunStep(Base):
    __tablename__ = "run_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    step_name = Column(String, nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="steps")

class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    media_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="artifacts")

# Create tables
def init_db():
    """Run Alembic migrations to ensure database schema is up to date.

    Handles three cases:
    1. Empty database: Runs all migrations from scratch
    2. Pre-Alembic database (tables exist but no alembic_version): Stamps to head
    3. Normal case: Applies any pending migrations
    """
    import logging
    from alembic.config import Config
    from alembic import command
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import inspect

    logger = logging.getLogger(__name__)

    # Suppress noisy Alembic logs - only show WARNING and above
    logging.getLogger('alembic').setLevel(logging.WARNING)
    logging.getLogger('alembic.runtime.migration').setLevel(logging.WARNING)

    try:
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

            # Check if tables exist but alembic_version doesn't (pre-Alembic database)
            inspector = inspect(conn)
            tables_exist = 'runs' in inspector.get_table_names()
            alembic_exists = 'alembic_version' in inspector.get_table_names()

        if current_rev is None and tables_exist and not alembic_exists:
            # Case 2: Tables were created by SQLAlchemy before Alembic was added
            logger.info("Existing database detected. Stamping as current version...")
            command.stamp(alembic_cfg, "head")
            logger.info("Database stamped successfully.")
        elif current_rev != head_rev:
            # Case 1 (empty db) or Case 3 (pending migrations)
            if current_rev is None:
                logger.info("Empty database. Creating schema via migrations...")
            else:
                logger.info(f"Applying migrations ({current_rev} -> {head_rev})...")
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations completed successfully.")
        # If current_rev == head_rev: already up to date, silent

    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        raise  # Don't fall back to create_all, let Alembic handle it
