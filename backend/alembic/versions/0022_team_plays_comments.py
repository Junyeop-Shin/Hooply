"""팀 전술 team_plays · 전술 댓글 tactic_comments (docs/07 8.2절, FR-57 · FR-60).

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-29

새 표만 만든다. 기존 데이터는 건드리지 않는다.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '0022'
down_revision: str | None = '0021'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'team_plays',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('team_id', sa.BigInteger(), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=30), nullable=False),
        sa.Column('summary', sa.String(length=80), nullable=False),
        sa.Column('defense', sa.String(length=4), nullable=False),
        sa.Column('situation', sa.String(length=12), nullable=False, server_default='half_court'),
        sa.Column('counter', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('body', postgresql.JSONB(), nullable=False),
        sa.Column('roles', postgresql.JSONB(), nullable=False),
        sa.Column('role_source', sa.String(length=10), nullable=False, server_default='RULE'),
        sa.Column('created_by', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('updated_by', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_team_plays_team_id', 'team_plays', ['team_id'])
    op.create_table(
        'tactic_comments',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('team_id', sa.BigInteger(), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('play_key', sa.String(length=40), nullable=False),
        sa.Column('author_player_id', sa.BigInteger(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('body', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_tactic_comments_team_play', 'tactic_comments', ['team_id', 'play_key', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_tactic_comments_team_play', table_name='tactic_comments')
    op.drop_table('tactic_comments')
    op.drop_index('ix_team_plays_team_id', table_name='team_plays')
    op.drop_table('team_plays')
