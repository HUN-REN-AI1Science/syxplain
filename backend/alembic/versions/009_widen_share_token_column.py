"""Widen public_share_token column from String(32) to String(64)

The share token generation uses 32 bytes of entropy via secrets.token_urlsafe(),
which produces ~43 character tokens. The previous String(32) column would
truncate these tokens, breaking share link lookups.

Revision ID: 009_widen_share_token_column
Revises: 008_add_input_data
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_widen_share_token_column'
down_revision: Union[str, None] = '008_add_input_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('runs', 'public_share_token',
                    existing_type=sa.String(32),
                    type_=sa.String(64),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column('runs', 'public_share_token',
                    existing_type=sa.String(64),
                    type_=sa.String(32),
                    existing_nullable=True)
