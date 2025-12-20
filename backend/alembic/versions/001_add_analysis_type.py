"""Add analysis_type column to runs table

Revision ID: 001_add_analysis_type
Revises: 000_initial_schema
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_analysis_type'
down_revision: Union[str, None] = '000_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add analysis_type column with default 'quick' for existing rows
    op.add_column('runs',
        sa.Column('analysis_type', sa.String(), server_default='quick', nullable=True)
    )


def downgrade() -> None:
    op.drop_column('runs', 'analysis_type')
