"""쿼터 대진 quarters.home_squad_no · away_squad_no (3팀 배정 — 쿼터마다 어느 두 팀이 뛰었는지).

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-29

기존 쿼터는 모두 2팀이라 1(블랙) · 2(화이트)로 채운다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0024'
down_revision: str | None = '0023'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('quarters', sa.Column('home_squad_no', sa.SmallInteger(), nullable=False, server_default='1'))
    op.add_column('quarters', sa.Column('away_squad_no', sa.SmallInteger(), nullable=False, server_default='2'))
    op.create_check_constraint('ck_quarters_distinct_squads', 'quarters', 'home_squad_no <> away_squad_no')


def downgrade() -> None:
    op.drop_constraint('ck_quarters_distinct_squads', 'quarters', type_='check')
    op.drop_column('quarters', 'away_squad_no')
    op.drop_column('quarters', 'home_squad_no')
