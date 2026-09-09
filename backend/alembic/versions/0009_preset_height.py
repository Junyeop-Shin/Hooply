"""guest_invite_presets.height_cm — 이전 초대 목록 불러오기에 키까지 채운다.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('guest_invite_presets', sa.Column('height_cm', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('guest_invite_presets', 'height_cm')
