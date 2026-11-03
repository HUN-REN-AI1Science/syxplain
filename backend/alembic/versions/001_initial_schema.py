"""Initial schema - fresh start after Supabase to Keycloak migration

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-02-25

Creates all tables matching current SQLAlchemy models.
User permissions are now managed via Keycloak realm roles
(syxplain-admin and the server-keys role, SERVER_KEYS_ROLE) — no user_permissions table needed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # files — uploaded CSV/Excel data
    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # runs — analysis runs with config, progress, and results
    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("analysis_type", sa.String(), server_default="quick"),
        sa.Column("slurm_job_ids", JSONB(), nullable=True),
        sa.Column("progress", sa.Integer(), server_default="0"),
        sa.Column("problem_description", JSONB(), nullable=False),
        sa.Column("csv_filename", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("results", JSONB(), nullable=True),
        sa.Column("public_share_token", sa.String(64), nullable=True, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("finish_time", sa.DateTime(), nullable=True),
        sa.Column("input_data", JSONB(), nullable=True),
    )

    # run_steps — pipeline step tracking
    op.create_table(
        "run_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # run_artifacts — generated files (plots, JSON outputs)
    op.create_table(
        "run_artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # audit_logs — admin action tracking
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_email", sa.String(255), nullable=False, index=True),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("target_type", sa.String(50), nullable=False, index=True),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("run_artifacts")
    op.drop_table("run_steps")
    op.drop_table("runs")
    op.drop_table("files")
