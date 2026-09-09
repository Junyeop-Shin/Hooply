"""guest_invite_presets — 플레이어별 게스트 초대 이력 ("이전 초대 목록 불러오기").

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'guest_invite_presets',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('team_id', sa.BigInteger(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=False),
        sa.Column('display_name', sa.String(length=50), nullable=False),
        sa.Column('skill_grade', sa.SmallInteger(), nullable=True),
        sa.Column('preferred_position', sa.String(length=2), nullable=True),
        sa.Column('playable_positions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('team_lock_request', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_player_id', sa.BigInteger(), nullable=True),
        sa.Column('use_count', sa.Integer(), server_default='1', nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_player_id'], ['players.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'created_by', 'display_name', name='uq_guest_invite_presets_owner_name'),
    )
    op.create_index(op.f('ix_guest_invite_presets_team_id'), 'guest_invite_presets', ['team_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_guest_invite_presets_team_id'), table_name='guest_invite_presets')
    op.drop_table('guest_invite_presets')
