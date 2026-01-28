"""Add user_permissions table for API key access control

Revision ID: 006_add_user_permissions
Revises: 005_add_execution_timestamps
Create Date: 2026-01-28

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '006_add_user_permissions'
down_revision: Union[str, None] = '005_add_execution_timestamps'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_permissions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column('use_hunren_keys', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('granted_by', sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('user_permissions')
