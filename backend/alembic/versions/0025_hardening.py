"""하드닝: 관리자 보정 오프셋 · 토큰 세대 · CHECK 제약 · 중복 인덱스 정리 · 팀 전술 FK · 활성 정렬 유일.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-02

운영 데이터 위에서 실패하지 않도록 썼다 — 고칠 수 있는 행은 먼저 고치고(repair-before-constrain),
CHECK 는 NOT VALID 로 붙인 뒤 어긋난 행이 없을 때만 VALIDATE 한다(남아 있으면 새 행만 검사하고 로그를 남긴다).

1) player_profiles.admin_adjust — 관리자 보정을 사전값과 따로 둔다. 재계산은 prior + admin_adjust 에서 출발한다
2) users.token_version — 비밀번호를 바꾸면 올라가 다른 기기의 토큰을 무효로 만든다
3) CHECK — 쿼터 점수(0~200) · 길이(1~10분) · 번호 · 대진, 팀 수(2·3), squad_no(1~3), 정렬 순위, 게스트 등급,
   선호 점수(0~1), 자기 자신 병합 금지, 일정 시각 순서
4) 다른 인덱스(유니크 · 복합)의 맨 앞 컬럼과 같은 단독 인덱스 9개를 지운다
5) 팀 전술을 가리키는 댓글 · 별표 · 자리 배치에 team_play_id FK(ON DELETE CASCADE) — play_key 에서 채우고,
   이미 지워진 팀 전술을 가리키던 행은 지운다. event_play_assignments.player_id · tactic_comments.author_player_id 인덱스
6) event_play_assignments UNIQUE(event_id, squad_no, play_key, player_id) — 중복을 먼저 지운다
7) manager_rankings 팀당 활성 버전 하나(부분 유니크) — 여러 개면 최신만 남기고 끈다
8) llm_results.created_at 인덱스 (60일 보관 청소)
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0025'
down_revision: str | None = '0024'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (인덱스, 테이블, 컬럼) — 같은 맨 앞 컬럼을 가진 유니크/복합 인덱스가 이미 있다 (괄호 안)
DUPLICATE_INDEXES = [
    ('ix_events_team_id', 'events', ['team_id']),  # ix_events_team_date (team_id, event_date, id)
    ('ix_quarters_event_id', 'quarters', ['event_id']),  # uq_quarters_event_no (event_id, quarter_no)
    ('ix_post_game_surveys_event_id', 'post_game_surveys', ['event_id']),  # uq_post_game_surveys_respondent (event_id, …)
    ('ix_player_positions_player_id', 'player_positions', ['player_id']),  # uq_player_positions_player_position (player_id, position)
    ('ix_chemistry_scores_a', 'chemistry_scores', ['player_a_id']),  # uq_chemistry_scores_pair (player_a_id, player_b_id)
    ('ix_guest_invite_presets_team_id', 'guest_invite_presets', ['team_id']),  # uq_guest_invite_presets_owner_name (team_id, …)
    ('ix_user_badges_user_id', 'user_badges', ['user_id']),  # uq_user_badges_code (user_id, code)
    ('ix_event_play_assignments_event_id', 'event_play_assignments', ['event_id']),  # uq_event_play_assignments_slot (event_id, …)
    ('ix_tactic_stars_team_id', 'tactic_stars', ['team_id']),  # uq_tactic_stars_team_play (team_id, play_key)
]

# (테이블, 이름, 조건, 먼저 고치는 SQL 또는 None)
CHECKS = [
    ('quarters', 'ck_quarters_score_range', 'black_score BETWEEN 0 AND 200 AND white_score BETWEEN 0 AND 200', None),
    ('quarters', 'ck_quarters_duration_range', 'duration_min BETWEEN 1 AND 10',
     'UPDATE quarters SET duration_min = LEAST(GREATEST(duration_min, 1), 10) WHERE duration_min NOT BETWEEN 1 AND 10'),
    ('quarters', 'ck_quarters_quarter_no', 'quarter_no >= 1', None),
    ('quarters', 'ck_quarters_squad_no', 'home_squad_no BETWEEN 1 AND 3 AND away_squad_no BETWEEN 1 AND 3', None),
    ('assignment_runs', 'ck_assignment_runs_team_count', 'team_count IN (2, 3)', None),
    ('assignment_squads', 'ck_assignment_squads_squad_no', 'squad_no BETWEEN 1 AND 3', None),
    ('assignment_constraints', 'ck_assignment_constraints_squad_no', 'squad_no IS NULL OR squad_no BETWEEN 1 AND 3', None),
    ('event_play_assignments', 'ck_event_play_assignments_squad_no', 'squad_no BETWEEN 1 AND 3', None),
    ('manager_ranking_entries', 'ck_ranking_entries_rank_no', 'rank_no >= 1', None),
    ('guest_invite_presets', 'ck_guest_invite_presets_skill_grade', 'skill_grade IS NULL OR skill_grade BETWEEN 1 AND 5',
     'UPDATE guest_invite_presets SET skill_grade = NULL WHERE skill_grade NOT BETWEEN 1 AND 5'),
    ('chemistry_scores', 'ck_chemistry_scores_pref_range', 'pref_score IS NULL OR pref_score BETWEEN 0 AND 1',
     'UPDATE chemistry_scores SET pref_score = LEAST(GREATEST(pref_score, 0), 1) WHERE pref_score NOT BETWEEN 0 AND 1'),
    ('players', 'ck_players_not_merged_into_self', 'merged_into_player_id <> id',
     'UPDATE players SET merged_into_player_id = NULL WHERE merged_into_player_id = id'),
    ('events', 'ck_events_time_order', 'start_time IS NULL OR end_time IS NULL OR end_time > start_time',
     'UPDATE events SET end_time = NULL WHERE start_time IS NOT NULL AND end_time IS NOT NULL AND end_time <= start_time'),
]

TEAM_PLAY_REFS = ['tactic_comments', 'tactic_stars', 'event_play_assignments']


def _add_check(table: str, name: str, expr: str) -> None:
    """NOT VALID 로 붙이고, 어긋난 행이 없을 때만 VALIDATE (있으면 새 행만 검사하고 로그를 남긴다)."""
    op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}')
    op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr}) NOT VALID')
    bad = op.get_bind().execute(sa.text(f'SELECT count(*) FROM {table} WHERE NOT ({expr})')).scalar()
    if bad:
        print(f'[0025] {table}.{name}: 조건에 맞지 않는 행 {bad}개 — NOT VALID 로 둔다 (새 행만 검사). 정리한 뒤 VALIDATE CONSTRAINT 하세요')
    else:
        op.execute(f'ALTER TABLE {table} VALIDATE CONSTRAINT {name}')


def upgrade() -> None:
    # 1) 2)
    op.add_column('player_profiles', sa.Column('admin_adjust', sa.Numeric(4, 1), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))

    # 3) CHECK — 예전 두 제약은 범위가 넓은 새 제약으로 바꾼다
    for table, name, expr, repair in CHECKS:
        if repair:
            op.execute(repair)
        _add_check(table, name, expr)
    op.execute('ALTER TABLE quarters DROP CONSTRAINT IF EXISTS ck_quarters_score_nonneg')
    op.execute('ALTER TABLE quarters DROP CONSTRAINT IF EXISTS ck_quarters_duration_positive')

    # 4)
    for name, _table, _cols in DUPLICATE_INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')

    # 5) 팀 전술 FK
    for table in TEAM_PLAY_REFS:
        op.add_column(table, sa.Column('team_play_id', sa.BigInteger(), nullable=True))
        op.execute(
            f"""
            UPDATE {table} t SET team_play_id = tp.id FROM team_plays tp
            WHERE t.play_key LIKE 'team:%' AND t.play_key = 'team:' || tp.id::text
            """
        )
        # 지워진 팀 전술을 가리키던 행 (예전에는 지울 때 play_key 로 같이 지웠지만 빠진 경로가 있었을 수 있다)
        op.execute(f"DELETE FROM {table} WHERE play_key LIKE 'team:%' AND team_play_id IS NULL")
        op.create_foreign_key(f'{table}_team_play_id_fkey', table, 'team_plays', ['team_play_id'], ['id'], ondelete='CASCADE')
        op.create_index(f'ix_{table}_team_play_id', table, ['team_play_id'])
    op.create_index('ix_event_play_assignments_player_id', 'event_play_assignments', ['player_id'])
    op.create_index('ix_tactic_comments_author_player_id', 'tactic_comments', ['author_player_id'])

    # 6) 한 전술 배치에서 한 사람은 한 자리 — 중복이 있으면 나중 행만 남긴다
    op.execute(
        """
        DELETE FROM event_play_assignments a USING event_play_assignments b
        WHERE a.event_id = b.event_id AND a.squad_no = b.squad_no AND a.play_key = b.play_key
          AND a.player_id = b.player_id AND a.id < b.id
        """
    )
    op.create_unique_constraint(
        'uq_event_play_assignments_player', 'event_play_assignments', ['event_id', 'squad_no', 'play_key', 'player_id'],
    )

    # 7) 팀당 활성 정렬 하나 — 최신(created_at, id 가장 큰 것)만 남기고 끈다
    op.execute(
        """
        UPDATE manager_rankings SET is_active = false
        WHERE is_active AND id NOT IN (
            SELECT DISTINCT ON (team_id) id FROM manager_rankings WHERE is_active ORDER BY team_id, created_at DESC, id DESC
        )
        """
    )
    op.create_index('uq_manager_rankings_active', 'manager_rankings', ['team_id'], unique=True, postgresql_where=sa.text('is_active'))

    # 8)
    op.create_index('ix_llm_results_created_at', 'llm_results', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_llm_results_created_at', table_name='llm_results')
    op.drop_index('uq_manager_rankings_active', table_name='manager_rankings')
    op.drop_constraint('uq_event_play_assignments_player', 'event_play_assignments', type_='unique')
    op.drop_index('ix_tactic_comments_author_player_id', table_name='tactic_comments')
    op.drop_index('ix_event_play_assignments_player_id', table_name='event_play_assignments')
    for table in TEAM_PLAY_REFS:
        op.drop_index(f'ix_{table}_team_play_id', table_name=table)
        op.drop_constraint(f'{table}_team_play_id_fkey', table, type_='foreignkey')
        op.drop_column(table, 'team_play_id')
    for name, table, cols in DUPLICATE_INDEXES:
        op.create_index(name, table, cols)
    op.create_check_constraint('ck_quarters_duration_positive', 'quarters', 'duration_min > 0')
    op.create_check_constraint('ck_quarters_score_nonneg', 'quarters', 'black_score >= 0 AND white_score >= 0')
    for table, name, _expr, _repair in reversed(CHECKS):
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}')
    op.drop_column('users', 'token_version')
    op.drop_column('player_profiles', 'admin_adjust')
