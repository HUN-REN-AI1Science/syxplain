"""Add public_share_token column to runs table

Revision ID: 003_add_public_share_token
Revises: 002_add_progress
Create Date: 2025-12-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_add_public_share_token'
down_revision: Union[str, None] = '002_add_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add public_share_token column to runs table
    op.add_column('runs', sa.Column('public_share_token', sa.String(32), nullable=True))

    # Create unique index for fast lookups (also ensures uniqueness)
    op.create_index('ix_runs_public_share_token', 'runs', ['public_share_token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_runs_public_share_token', table_name='runs')
    op.drop_column('runs', 'public_share_token')
