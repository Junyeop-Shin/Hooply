"""피어 투표 재설계 (피어 투표 설계): reason_tag, target_side NULL 허용, chemistry_scores.together_events.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08

- post_game_votes.reason_tag  : PLAY_AGAIN 을 고른 이유 (PASS / DEFENSE_HELP / TEMPO / OTHER), 선택
- post_game_votes.target_side : 확정 배정이 없던 회차는 알 수 없으므로 NULL 허용
- chemistry_scores.together_events : pref_score 정규화 분모 (함께 참석한 회차 수)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'post_game_votes',
        sa.Column(
            'reason_tag',
            sa.Enum('PASS', 'DEFENSE_HELP', 'TEMPO', 'OTHER', name='ck_reasontag', native_enum=False, create_constraint=True, length=20),
            nullable=True,
        ),
    )
    op.alter_column('post_game_votes', 'target_side', existing_type=sa.String(length=10), nullable=True)
    op.add_column('chemistry_scores', sa.Column('together_events', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('chemistry_scores', 'together_events')
    op.execute("DELETE FROM post_game_votes WHERE target_side IS NULL")
    op.alter_column('post_game_votes', 'target_side', existing_type=sa.String(length=10), nullable=False)
    op.drop_constraint('ck_reasontag', 'post_game_votes', type_='check')
    op.drop_column('post_game_votes', 'reason_tag')
