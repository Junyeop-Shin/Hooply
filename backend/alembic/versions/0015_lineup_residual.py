"""quarter_lineups.residual — 쿼터별 기여도(실제 마진 − 기대 마진)를 회차 단위로 남긴다.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-14

리더보드의 "기여 점수" 가 기간을 골라도 늘 같은 값이던 원인: 프로필에 쌓아 둔 누적 총합만 있어서
기간으로 쪼갤 수 없었다. 쿼터마다 몫을 남겨 두면 월별 합계를 낼 수 있다.

기존 행은 0 으로 채운 뒤, 배포 시 실력 재계산이 돌면서 실제 값으로 다시 쓰인다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('quarter_lineups', sa.Column('residual', sa.Numeric(6, 2), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('quarter_lineups', 'residual')
