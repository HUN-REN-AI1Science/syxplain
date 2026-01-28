"""Add slurm_job_ids column to runs table for cancellation support

Revision ID: 004_add_cancellation_support
Revises: 003_add_public_share_token
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '004_add_cancellation_support'
down_revision: Union[str, None] = '003_add_public_share_token'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add slurm_job_ids column to runs table
    # Structure: {"shap_job_id": "uuid-string", "pysr_job_id": "uuid-string"}
    op.add_column('runs', sa.Column('slurm_job_ids', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'slurm_job_ids')
