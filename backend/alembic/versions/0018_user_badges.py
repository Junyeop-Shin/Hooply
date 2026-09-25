"""배지 테이블 user_badges (기록 탭).

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-25

사용자 단위 성취 표시. 코드 목록은 app/services/badge_service.py 의 BADGES 가 정본이고 DB 는 획득 사실과 시각만 보관한다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user_badges',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(length=40), nullable=False),
        sa.Column('earned_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('user_id', 'code', name='uq_user_badges_code'),
    )
    op.create_index('ix_user_badges_user_id', 'user_badges', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_user_badges_user_id', table_name='user_badges')
    op.drop_table('user_badges')
