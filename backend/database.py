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
    status = Column(String, default="pending")  # pending, running, completed, failed, timeout
    analysis_type = Column(String, default="quick")  # "quick" or "deep"
    progress = Column(Integer, default=0)  # 0-100 percentage
    problem_description = Column(JSONB, nullable=False)
    csv_filename = Column(String, nullable=False) # Store filename for reference
    error = Column(Text, nullable=True)
    results = Column(JSONB, nullable=True)
    public_share_token = Column(String(32), nullable=True, unique=True, index=True)
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

    Simply checks alembic_version table and applies any pending migrations.
    """
    import logging
    from alembic.config import Config
    from alembic import command

    logger = logging.getLogger(__name__)

    try:
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully.")

    except Exception as e:
        logger.error(f"Database migration failed: {e}")
        raise
