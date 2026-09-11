"""guest_claims — 회원이 스스로 "이 게스트 기록은 내 것" 을 확인/거절한 이력. 거절한 게스트는 다시 묻지 않는다.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'guest_claims',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('guest_player_id', sa.BigInteger(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('guest_player_id', 'user_id', name='uq_guest_claims_guest_user'),
        sa.CheckConstraint("status IN ('CONFIRMED','DECLINED')", name='ck_guest_claims_status'),
    )
    op.create_index('ix_guest_claims_user_id', 'guest_claims', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_guest_claims_user_id', table_name='guest_claims')
    op.drop_table('guest_claims')
