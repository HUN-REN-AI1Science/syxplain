"""Add progress column to runs table

Revision ID: 002_add_progress
Revises: 001_add_analysis_type
Create Date: 2025-12-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_progress'
down_revision: Union[str, None] = '001_add_analysis_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add progress column with default 0 for existing rows
    op.add_column('runs',
        sa.Column('progress', sa.Integer(), server_default='0', nullable=True)
    )


def downgrade() -> None:
    op.drop_column('runs', 'progress')
