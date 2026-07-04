"""Add error_details column to runs

Revision ID: 003_add_run_error_details
Revises: 002_add_api_keys
Create Date: 2026-07-05

Adds a structured error_details JSONB column to runs so failed runs
can show users what went wrong (category, pipeline stage, traceback).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "003_add_run_error_details"
down_revision: str | None = "002_add_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("error_details", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "error_details")
