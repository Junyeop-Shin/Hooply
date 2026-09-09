"""설문 v2 시드·활성화, 팀별 자기 위치(self_rank_level) 컬럼, users.birth_year 제거.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08

무엇이 바뀌는가 (사용자 피드백 반영)
  1. 설문 템플릿 **v2** 를 넣고 활성화한다. v1 은 비활성으로 남겨 v1 응답의 배점을 보존한다 (8.6절 버전 관리).
     v2 변경: 키 문항 삭제(가입 시 받는 height_cm 사용), 경기 수준 5단계, 선호 포지션 문항을
     "가능 포지션을 선호 순서대로" 로 통합, 성향·체력 문구 정리, 동호회 내 상대 위치(E3) 제거.
  2. `player_profiles.self_rank_level` 추가 — 구 E3 를 팀 가입 **후** 팀별로 묻는다.
  3. `users.birth_year` 와 CHECK 제약 삭제 — 출생연도를 받지 않는다.

적용 / 되돌리기
  alembic upgrade head      # 0002 → 0003
  alembic downgrade 0002    # v2 템플릿 삭제 후 v1 재활성, 컬럼 복원 (birth_year 값은 복구되지 않음)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.survey_seed import seed_survey_v2, templates_t

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'player_profiles',
        sa.Column(
            'self_rank_level',
            sa.Enum('TOP10', 'TOP30', 'MID', 'BOT30', 'BOT10', name='ck_selfranklevel', native_enum=False,
                    create_constraint=True, length=5),
            nullable=True,
        ),
    )
    op.drop_constraint('ck_users_birth_year', 'users', type_='check')
    op.drop_column('users', 'birth_year')
    seed_survey_v2(op.get_bind())


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM survey_templates WHERE version = 2"))  # CASCADE 로 문항·선택지·응답 삭제
    conn.execute(sa.update(templates_t).where(templates_t.c.version == 1).values(is_active=True))
    op.add_column('users', sa.Column('birth_year', sa.SmallInteger(), nullable=True))
    op.create_check_constraint('ck_users_birth_year', 'users', 'birth_year IS NULL OR birth_year BETWEEN 1940 AND 2100')
    op.drop_constraint('ck_selfranklevel', 'player_profiles', type_='check')
    op.drop_column('player_profiles', 'self_rank_level')
