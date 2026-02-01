"""
SQLAlchemy ORM models for the Syxplain database.

These models represent the database tables and their relationships.
Separated from connection management for cleaner architecture.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class File(Base):
    """
    Represents an uploaded file (CSV or Excel) stored in the database.

    Files are associated with a user and can be referenced by multiple runs.
    """

    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    filename = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    media_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<File(id={self.id}, filename='{self.filename}')>"


class Run(Base):
    """
    Represents an analysis run with its configuration and results.

    A run is created when a user submits an analysis request and
    tracks the progress through completion or failure.
    """

    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(
        String, default="pending"
    )  # pending, running, completed, failed, timeout, cancelled
    analysis_type = Column(String, default="quick")  # "quick" or "deep"
    slurm_job_ids = Column(JSONB, nullable=True)  # {"shap_job_id": "...", "pysr_job_id": "..."}
    progress = Column(Integer, default=0)  # 0-100 percentage
    problem_description = Column(JSONB, nullable=False)
    csv_filename = Column(String, nullable=False)  # Store filename for reference
    error = Column(Text, nullable=True)
    results = Column(JSONB, nullable=True)
    public_share_token = Column(String(32), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    start_time = Column(DateTime, nullable=True)  # Set when status becomes "running"
    finish_time = Column(DateTime, nullable=True)  # Set when status becomes terminal

    # Relationships with cascade delete
    steps = relationship("RunStep", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("RunArtifact", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Run(id={self.id}, status='{self.status}')>"

    @property
    def target_variable(self) -> str | None:
        """Extract target variable from problem description."""
        if self.problem_description and isinstance(self.problem_description, dict):
            return self.problem_description.get("target_variable")
        return None

    @property
    def is_shared(self) -> bool:
        """Check if the run has a public share token."""
        return self.public_share_token is not None


class RunStep(Base):
    """
    Represents a step in the analysis process.

    Steps track the progress of the analysis through different phases
    with their associated payload data.
    """

    __tablename__ = "run_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    step_name = Column(String, nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="steps")

    def __repr__(self) -> str:
        return f"<RunStep(run_id={self.run_id}, step={self.step_number}, name='{self.step_name}')>"


class RunArtifact(Base):
    """
    Represents a file artifact generated during analysis.

    Artifacts include generated visualizations, JSON outputs,
    and other downloadable files.
    """

    __tablename__ = "run_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    media_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="artifacts")

    def __repr__(self) -> str:
        return f"<RunArtifact(run_id={self.run_id}, filename='{self.filename}')>"


class UserPermission(Base):
    """
    Represents user permissions for API key access.

    Users with use_hunren_keys=True can use built-in HUN-REN API keys.
    Users without this permission must provide their own OpenAI API key.
    """

    __tablename__ = "user_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    use_hunren_keys = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow, nullable=True)
    granted_by = Column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<UserPermission(user_id={self.user_id}, use_hunren_keys={self.use_hunren_keys})>"


class AuditLog(Base):
    """
    Represents an audit log entry for admin actions.

    Tracks all admin actions for accountability and compliance.
    """

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_email = Column(String(255), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_id = Column(String(255), nullable=False)
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog(admin={self.admin_email}, action={self.action}, target={self.target_type}/{self.target_id})>"
