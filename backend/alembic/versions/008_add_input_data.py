"""Add input_data column to runs table for Slurm worker input storage

Revision ID: 008_add_input_data
Revises: 007_add_audit_logs
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '008_add_input_data'
down_revision: Union[str, None] = '007_add_audit_logs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('input_data', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'input_data')
