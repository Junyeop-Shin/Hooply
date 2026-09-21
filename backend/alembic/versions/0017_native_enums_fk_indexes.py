"""상태값 컬럼을 PostgreSQL ENUM 타입으로 · 자주 쓰는 외래키에 인덱스.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-21

1) 지금까지 상태값(팀 상태·역할·포지션 등 21종)은 VARCHAR + CHECK 로 저장했다. 값은 똑같이 막히지만
   스키마만 봐서는 "이 컬럼이 열거형이다" 가 드러나지 않고, 허용값이 CHECK 식 안에 흩어져 있다.
   전용 ENUM 타입으로 바꾸면 타입 이름 자체가 문서가 되고(`team_status_enum`), 값 목록을 한 곳에서 관리한다.
   변환은 `USING col::text::<enum>` 으로 기존 값을 그대로 옮기고, 이제 불필요한 값 목록 CHECK 는 지운다.
   서버 기본값이 있는 컬럼은 기본값을 잠시 떼었다가 ENUM 값으로 다시 붙인다 (문자열 기본값은 자동 변환되지 않는다).
   값을 나중에 추가할 때는 `ALTER TYPE ... ADD VALUE` 를 쓴다 (트랜잭션 밖에서 실행해야 한다 — 다음 마이그레이션의 주의점).

2) 외래키 컬럼에는 인덱스가 자동으로 생기지 않는다. 조회 조건이나 ON DELETE 검사에 실제로 쓰이는 컬럼에 인덱스를 건다.
   등록자·기록자 같은 감사용 `*_by` 컬럼은 조회 조건으로 쓰이지 않고 사용자를 물리 삭제하지 않으므로 두지 않는다.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (타입 이름, 값 목록) — 값은 app/models/enums.py 의 StrEnum 과 같아야 한다
ENUMS: dict[str, tuple[str, ...]] = {
    'global_role_enum': ('ADMIN', 'USER'),
    'auth_provider_enum': ('LOCAL', 'KAKAO'),
    'team_status_enum': ('PENDING', 'ACTIVE', 'ARCHIVED'),
    'approval_status_enum': ('PENDING', 'APPROVED', 'REJECTED'),
    'player_kind_enum': ('MEMBER', 'GUEST'),
    'team_role_enum': ('MANAGER', 'PLAYER'),
    'player_status_enum': ('ACTIVE', 'LEFT', 'REMOVED'),
    'position_enum': ('PG', 'SG', 'SF', 'PF', 'C'),
    'prior_source_enum': ('SURVEY', 'MANAGER', 'DEFAULT'),
    'self_rank_level_enum': ('TOP10', 'TOP30', 'MID', 'BOT30', 'BOT10'),
    'rating_source_enum': ('SURVEY', 'MANAGER_SORT', 'RESIDUAL', 'PEER_VOTE', 'MANAGER_ADJUST', 'ADMIN_ADJUST', 'MERGE'),
    'answer_type_enum': ('STEPPER', 'ANCHOR_4', 'MULTI_CHIP', 'ORDINAL_5', 'SINGLE_CHOICE', 'TRIO'),
    'event_status_enum': ('OPEN', 'CLOSED', 'DONE', 'CANCELED'),
    'attendance_status_enum': ('ATTEND', 'ABSENT', 'PENDING'),
    'constraint_type_enum': ('LOCK', 'SEPARATE', 'PIN'),
    'strategy_enum': ('SKILL', 'CHEMISTRY', 'BALANCED'),
    'side_enum': ('BLACK', 'WHITE'),
    'vote_type_enum': ('BEST_PERFORMER', 'PLAY_AGAIN'),
    'reason_tag_enum': ('PASS', 'DEFENSE_HELP', 'TEMPO', 'OTHER'),
    'target_side_enum': ('SAME_TEAM', 'OPPONENT'),
    'claim_status_enum': ('CONFIRMED', 'DECLINED'),
}

# (테이블, 컬럼, 타입 이름, 지울 값 목록 CHECK 이름, VARCHAR 길이(되돌릴 때), 서버 기본값)
COLUMNS: list[tuple[str, str, str, str, int, str | None]] = [
    ('users', 'global_role', 'global_role_enum', 'ck_globalrole', 10, 'USER'),
    ('auth_identities', 'provider', 'auth_provider_enum', 'ck_authprovider', 10, None),
    ('teams', 'status', 'team_status_enum', 'ck_teamstatus', 10, 'PENDING'),
    ('teams', 'approval_status', 'approval_status_enum', 'ck_teams_approval_status', 10, 'PENDING'),
    ('players', 'kind', 'player_kind_enum', 'ck_playerkind', 10, None),
    ('players', 'role', 'team_role_enum', 'ck_teamrole', 10, 'PLAYER'),
    ('players', 'status', 'player_status_enum', 'ck_playerstatus', 10, 'ACTIVE'),
    ('events', 'status', 'event_status_enum', 'ck_eventstatus', 10, 'OPEN'),
    ('event_attendances', 'status', 'attendance_status_enum', 'ck_attendancestatus', 10, 'PENDING'),
    ('player_positions', 'position', 'position_enum', 'ck_position', 2, None),
    ('player_profiles', 'prior_source', 'prior_source_enum', 'ck_priorsource', 20, None),
    ('player_profiles', 'self_rank_level', 'self_rank_level_enum', 'ck_selfranklevel', 5, None),
    ('skill_rating_history', 'source', 'rating_source_enum', 'ck_ratingsource', 20, None),
    ('survey_questions', 'answer_type', 'answer_type_enum', 'ck_answertype', 15, None),
    ('assignment_candidates', 'strategy', 'strategy_enum', 'ck_strategy', 10, None),
    ('assignment_constraints', 'type', 'constraint_type_enum', 'ck_constrainttype', 10, None),
    ('assignment_slots', 'assigned_position', 'position_enum', 'ck_position', 2, None),
    ('quarter_lineups', 'side', 'side_enum', 'ck_side', 5, None),
    ('quarter_lineups', 'position', 'position_enum', 'ck_position', 2, None),
    ('post_game_votes', 'vote_type', 'vote_type_enum', 'ck_votetype', 15, None),
    ('post_game_votes', 'target_side', 'target_side_enum', 'ck_targetside', 10, None),
    ('post_game_votes', 'reason_tag', 'reason_tag_enum', 'ck_reasontag', 20, None),
    ('guest_claims', 'status', 'claim_status_enum', 'ck_guest_claims_status', 10, None),
]

# 조회 조건 · ON DELETE 검사에 쓰이는 외래키
FK_INDEXES: list[tuple[str, str, str]] = [
    ('ix_revoked_tokens_user_id', 'revoked_tokens', 'user_id'),                           # 계정 삭제 CASCADE
    ('ix_users_primary_team_id', 'users', 'primary_team_id'),                             # 팀 삭제 SET NULL
    ('ix_teams_owner_user_id', 'teams', 'owner_user_id'),                                 # 팀장 조회
    ('ix_event_attendances_lock_request', 'event_attendances', 'team_lock_request_player_id'),  # 묶기 제안 · 게스트 정리
    ('ix_assignment_constraints_player_id', 'assignment_constraints', 'player_id'),       # 게스트 정리 · 제약 조회
    ('ix_manager_ranking_entries_player_id', 'manager_ranking_entries', 'player_id'),     # 선수 상세(정렬 순위) · 게스트 정리
    ('ix_post_game_surveys_respondent', 'post_game_surveys', 'respondent_player_id'),     # 내 투표 여부 · 게스트 정리
    ('ix_guest_invite_presets_last_player', 'guest_invite_presets', 'last_player_id'),    # 게스트 삭제 SET NULL
    ('ix_survey_answers_question_id', 'survey_answers', 'question_id'),                   # 앵커 재보정 집계 (8.6절)
]


def _check_sql(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    for name, values in ENUMS.items():
        op.execute(f"CREATE TYPE {name} AS ENUM ({', '.join(repr(v) for v in values)})")
    for table, column, enum, check, _length, default in COLUMNS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {check}")
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {enum} USING {column}::text::{enum}")
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'::{enum}")
    for index, table, column in FK_INDEXES:
        op.create_index(index, table, [column])


def downgrade() -> None:
    for index, table, _column in reversed(FK_INDEXES):
        op.drop_index(index, table_name=table)
    for table, column, enum, check, length, default in reversed(COLUMNS):
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR({length}) USING {column}::text")
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
        op.create_check_constraint(check, table, sa.text(_check_sql(column, ENUMS[enum])))
    for name in reversed(ENUMS):
        op.execute(f"DROP TYPE {name}")
