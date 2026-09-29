"""전술 이름표 테이블 event_play_assignments (docs/07 8.2절).

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-29

그날 팀별로 전술 슬롯에 앉힌 선수. 전술 정의는 app/tactics/presets.py 가 정본이라 DB 에는 play_key 만 둔다.
새 표만 만들고 기존 데이터는 건드리지 않는다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0020'
down_revision: str | None = '0019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'event_play_assignments',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('event_id', sa.BigInteger(), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('squad_no', sa.SmallInteger(), nullable=False),
        sa.Column('play_key', sa.String(length=40), nullable=False),
        sa.Column('slot', sa.SmallInteger(), nullable=False),
        sa.Column('player_id', sa.BigInteger(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('assigned_by', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('event_id', 'squad_no', 'play_key', 'slot', name='uq_event_play_assignments_slot'),
        sa.CheckConstraint('slot BETWEEN 1 AND 5', name='ck_event_play_assignments_slot'),
    )
    op.create_index('ix_event_play_assignments_event_id', 'event_play_assignments', ['event_id'])


def downgrade() -> None:
    op.drop_index('ix_event_play_assignments_event_id', table_name='event_play_assignments')
    op.drop_table('event_play_assignments')
