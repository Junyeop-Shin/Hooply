"""users.position_prefs — 사용자 단위 선호 포지션 순서 (프로필 수정의 원본).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08

왜 필요한가: 포지션은 팀별 `player_positions` 행에 저장되는데, 팀이 없는 사용자는 행이 없어 프로필에서
수정해도 저장할 곳이 없었다 (버그). 계정에 선호 순서 배열을 두고, 설문 제출·프로필 수정이 이 값을 갱신하며
팀 가입 시 이 값으로 행을 만든다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('position_prefs', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'position_prefs')
