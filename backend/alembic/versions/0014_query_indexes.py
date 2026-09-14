"""조회 성능 인덱스 두 개.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-14

1) events(team_id, event_date, id) — 일정 목록과 실력 재계산이 모두 "팀으로 좁혀 날짜순" 이다.
   지금은 팀으로만 좁힌 뒤 매번 정렬한다. 회차가 쌓일수록 이 정렬 비용이 커진다.
2) players(merged_into_player_id) WHERE NOT NULL — 병합된 게스트를 거슬러 올라가는 조회가
   지금은 players 전체를 훑는다. 값이 있는 행만 담아 인덱스를 작게 유지한다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index('ix_events_team_date', 'events', ['team_id', 'event_date', 'id'])
    op.create_index(
        'ix_players_merged_into', 'players', ['merged_into_player_id'],
        postgresql_where=sa.text('merged_into_player_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_players_merged_into', table_name='players')
    op.drop_index('ix_events_team_date', table_name='events')
