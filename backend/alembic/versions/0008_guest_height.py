"""players.height_cm — 게스트 키 (회원은 users.height_cm). 팀 평균 신장 계산에 게스트도 포함.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('players', sa.Column('height_cm', sa.SmallInteger(), nullable=True))
    op.create_check_constraint('ck_players_height_cm', 'players', 'height_cm IS NULL OR height_cm BETWEEN 120 AND 250')


def downgrade() -> None:
    op.drop_constraint('ck_players_height_cm', 'players', type_='check')
    op.drop_column('players', 'height_cm')
