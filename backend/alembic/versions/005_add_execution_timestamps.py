"""Add start_time and finish_time columns to runs table for execution timing

Revision ID: 005_add_execution_timestamps
Revises: 004_add_cancellation_support
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_add_execution_timestamps'
down_revision: Union[str, None] = '004_add_cancellation_support'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add start_time - set when status becomes "running"
    op.add_column('runs', sa.Column('start_time', sa.DateTime, nullable=True))
    # Add finish_time - set when status becomes terminal (completed, failed, timeout, cancelled)
    op.add_column('runs', sa.Column('finish_time', sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'finish_time')
    op.drop_column('runs', 'start_time')
