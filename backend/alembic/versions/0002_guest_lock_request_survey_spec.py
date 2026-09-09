"""게스트 묶기 요청 컬럼 + 온보딩 설문 테이블을 스펙 형태로 교체하고 v1 문항을 시드한다.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08

무엇이 바뀌는가
  1. 게스트 기능 설계 — `event_attendances.team_lock_request_player_id` (FK → players) 추가.
     게스트 등록자가 "나와 같은 팀으로" 를 표시한 요청. 강제 제약이 아니며 매니저가 배정 화면에서 승인한다.
  2. 설문 설계 — 설문 5개 테이블을 스펙의 컬럼 구조로 **드롭 후 재생성**한다.
     (question_text / answer_type 6종 / display_order / prior_weight, option_order / score_value,
      responses UNIQUE(user_id) 1인 1회, answers 는 문항당 1행 + selected_option_ids JSONB)
     0001 시점에는 설문 응답이 존재할 수 없었으므로(엔드포인트가 501) 데이터 이관은 없다.
  3. `app/db/survey_seed.py` 의 v1 14문항(D3 는 D3A/D3B 두 행)을 시드하고 활성화한다.

적용 / 되돌리기
  alembic upgrade head      # 0001 → 0002
  alembic downgrade 0001    # 설문 테이블을 0001 구조로 되돌린다 (응답 데이터는 사라진다)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.db.survey_seed import seed_survey_v1

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_SURVEY_TABLES = ('survey_answers', 'survey_options', 'survey_responses', 'survey_questions', 'survey_templates')
_FK_LOCK = 'fk_event_attendances_lock_request_player'


def upgrade() -> None:
    # 1) 0001 구조의 설문 테이블 제거 (응답 데이터 없음 — 엔드포인트가 스켈레톤이었다)
    for t in _OLD_SURVEY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS {t} CASCADE')

    # 2) 스펙 구조로 재생성
    op.create_table('survey_templates',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_table('survey_questions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('template_id', sa.BigInteger(), nullable=False),
    sa.Column('section', sa.String(length=1), nullable=False),
    sa.Column('code', sa.String(length=10), nullable=False),
    sa.Column('question_text', sa.Text(), nullable=False),
    sa.Column('answer_type', sa.Enum('STEPPER', 'ANCHOR_4', 'MULTI_CHIP', 'ORDINAL_5', 'SINGLE_CHOICE', 'TRIO', name='ck_answertype', native_enum=False, create_constraint=True, length=15), nullable=False),
    sa.Column('display_order', sa.SmallInteger(), nullable=False),
    sa.Column('prior_weight', sa.Numeric(precision=4, scale=3), nullable=True),
    sa.Column('help_text', sa.Text(), nullable=True),
    sa.Column('group_label', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['template_id'], ['survey_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('template_id', 'code', name='uq_survey_questions_code')
    )
    op.create_table('survey_responses',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('template_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['template_id'], ['survey_templates.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', name='uq_survey_responses_user')
    )
    op.create_table('survey_answers',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('response_id', sa.BigInteger(), nullable=False),
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('selected_option_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('numeric_value', sa.Numeric(precision=6, scale=1), nullable=True),
    sa.ForeignKeyConstraint(['question_id'], ['survey_questions.id'], ),
    sa.ForeignKeyConstraint(['response_id'], ['survey_responses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('response_id', 'question_id', name='uq_survey_answers_question')
    )
    op.create_table('survey_options',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('option_order', sa.SmallInteger(), nullable=False),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('score_value', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['survey_questions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('question_id', 'code', name='uq_survey_options_code')
    )

    # 3) 게스트 묶기 요청
    op.add_column('event_attendances', sa.Column('team_lock_request_player_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(_FK_LOCK, 'event_attendances', 'players', ['team_lock_request_player_id'], ['id'])

    # 4) v1 문항 시드
    seed_survey_v1(op.get_bind())


def downgrade() -> None:
    op.drop_constraint(_FK_LOCK, 'event_attendances', type_='foreignkey')
    op.drop_column('event_attendances', 'team_lock_request_player_id')

    for t in _OLD_SURVEY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS {t} CASCADE')

    # 0001 구조 복원 (0001_initial_schema.py 의 정의와 동일)
    op.create_table('survey_templates',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_table('survey_questions',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('template_id', sa.BigInteger(), nullable=False),
    sa.Column('code', sa.String(length=10), nullable=False),
    sa.Column('section', sa.String(length=1), nullable=False),
    sa.Column('order_no', sa.SmallInteger(), nullable=False),
    sa.Column('question_type', sa.Enum('NUMBER', 'ANCHOR4', 'MULTI', 'ORDINAL', 'SINGLE', name='ck_questiontype', native_enum=False, create_constraint=True, length=10), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('help_text', sa.Text(), nullable=True),
    sa.Column('max_select', sa.SmallInteger(), nullable=True),
    sa.ForeignKeyConstraint(['template_id'], ['survey_templates.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('template_id', 'code', name='uq_survey_questions_code')
    )
    op.create_table('survey_responses',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('template_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['template_id'], ['survey_templates.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('template_id', 'user_id', name='uq_survey_responses_user')
    )
    op.create_index(op.f('ix_survey_responses_user_id'), 'survey_responses', ['user_id'], unique=False)
    op.create_table('survey_options',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('order_no', sa.SmallInteger(), nullable=False),
    sa.Column('score', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['survey_questions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('question_id', 'code', name='uq_survey_options_code')
    )
    op.create_table('survey_answers',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('response_id', sa.BigInteger(), nullable=False),
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('option_id', sa.BigInteger(), nullable=True),
    sa.Column('value_num', sa.Numeric(precision=6, scale=1), nullable=True),
    sa.ForeignKeyConstraint(['option_id'], ['survey_options.id'], ),
    sa.ForeignKeyConstraint(['question_id'], ['survey_questions.id'], ),
    sa.ForeignKeyConstraint(['response_id'], ['survey_responses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('response_id', 'question_id', 'option_id', name='uq_survey_answers_option')
    )
