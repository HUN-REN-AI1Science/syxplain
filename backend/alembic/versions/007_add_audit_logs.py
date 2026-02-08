"""Add audit_logs table for admin action tracking

Revision ID: 007_add_audit_logs
Revises: 006_add_user_permissions
Create Date: 2026-02-01

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '007_add_audit_logs'
down_revision: Union[str, None] = '006_add_user_permissions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('admin_email', sa.String(255), nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('target_type', sa.String(50), nullable=False, index=True),
        sa.Column('target_id', sa.String(255), nullable=False),
        sa.Column('details', JSONB, nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.utcnow, index=True),
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
