"""게스트가 고른 실력 등급(1~5)을 게스트 행에 둔다: players.guest_grade.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-16

지금까지 등급 1~5 는 사전값(prior_overall)으로 바꾼 뒤 버렸고, 원래 값은 초대한 사람마다 따로 둔 사본
(guest_invite_presets)에만 남았다. 그래서 다른 사람이 등급을 고친 뒤 내가 사본을 골라 다시 초대하면 옛 등급으로
되돌아갔고, 남이 부른 게스트를 고칠 때는 지금 등급을 채워 보여 줄 수 없었다. 이제 게스트 행 하나가 정본이다.

채우기: 등급을 바꿀 때마다 남는 변동 이력(`게스트 실력 N단계`)의 가장 최근 값. 이력이 없는 게스트만 사본의 최근 값.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0028'
down_revision: str | None = '0027'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('players', sa.Column('guest_grade', sa.SmallInteger(), nullable=True))
    op.create_check_constraint('ck_players_guest_grade', 'players', 'guest_grade IS NULL OR guest_grade BETWEEN 1 AND 5')
    # 가장 최근 등급 이력. "미지정(팀 평균으로 계산)" 이 마지막이면 NULL 로 남는다
    op.execute("""
        UPDATE players p SET guest_grade = sub.g
        FROM (
            SELECT DISTINCT ON (h.player_id) h.player_id,
                   substring(h.reason from '게스트 실력 ([1-5])단계')::smallint AS g
            FROM skill_rating_history h
            WHERE h.reason LIKE '게스트 실력 %'
            ORDER BY h.player_id, h.created_at DESC, h.id DESC
        ) sub
        WHERE p.id = sub.player_id AND p.kind = 'GUEST' AND sub.g IS NOT NULL
    """)
    op.execute("""
        UPDATE players p SET guest_grade = sub.g
        FROM (
            SELECT DISTINCT ON (last_player_id) last_player_id, skill_grade AS g
            FROM guest_invite_presets
            WHERE last_player_id IS NOT NULL AND skill_grade IS NOT NULL
            ORDER BY last_player_id, last_used_at DESC
        ) sub
        WHERE p.id = sub.last_player_id AND p.kind = 'GUEST' AND p.guest_grade IS NULL
          AND NOT EXISTS (SELECT 1 FROM skill_rating_history h WHERE h.player_id = p.id AND h.reason LIKE '게스트 실력 %')
    """)


def downgrade() -> None:
    op.drop_constraint('ck_players_guest_grade', 'players', type_='check')
    op.drop_column('players', 'guest_grade')
