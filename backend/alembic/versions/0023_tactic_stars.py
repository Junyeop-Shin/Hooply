"""매니저가 별표한 전술 tactic_stars (docs/07 8.2절, FR-61).

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-29

새 표만 만든다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0023'
down_revision: str | None = '0022'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'tactic_stars',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('team_id', sa.BigInteger(), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('play_key', sa.String(length=40), nullable=False),
        sa.Column('starred_by', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('team_id', 'play_key', name='uq_tactic_stars_team_play'),
    )
    op.create_index('ix_tactic_stars_team_id', 'tactic_stars', ['team_id'])


def downgrade() -> None:
    op.drop_index('ix_tactic_stars_team_id', table_name='tactic_stars')
    op.drop_table('tactic_stars')
