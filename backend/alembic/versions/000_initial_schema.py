"""Initial schema - create all base tables

Revision ID: 000_initial_schema
Revises:
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '000_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create files table
    op.create_table(
        'files',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('media_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # Create runs table
    op.create_table(
        'runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('status', sa.String(), server_default='pending'),
        sa.Column('problem_description', JSONB(), nullable=False),
        sa.Column('csv_filename', sa.String(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('results', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # Create run_artifacts table
    op.create_table(
        'run_artifacts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('runs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('media_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # Create run_steps table
    op.create_table(
        'run_steps',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', UUID(as_uuid=True), sa.ForeignKey('runs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('step_name', sa.String(), nullable=False),
        sa.Column('payload', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('run_steps')
    op.drop_table('run_artifacts')
    op.drop_table('runs')
    op.drop_table('files')
