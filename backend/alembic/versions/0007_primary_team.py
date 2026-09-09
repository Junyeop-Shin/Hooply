"""users.primary_team_id — 여러 팀에 속한 사용자가 프로필에서 우선 볼 팀 (홈 화면 "메인으로" 설정).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('primary_team_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_users_primary_team', 'users', 'teams', ['primary_team_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_users_primary_team', 'users', type_='foreignkey')
    op.drop_column('users', 'primary_team_id')
