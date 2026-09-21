"""온보딩 설문 (설계서 8장 · 설문 설계): 템플릿 버전 관리 + 응답.

테이블 구조 (설계서 6.1절 "설문" 그룹)
  survey_templates  ─1:N─ survey_questions ─1:N─ survey_options   … 문항 정의 (버전별, 시드 데이터)
  survey_responses  ─1:N─ survey_answers                          … 사용자 응답 (1인 1회)

왜 문항을 DB 에 두는가: 8.6절 앵커 재보정 때문이다. 데이터가 쌓이면 각 선택지를 고른 사람들의 실측
실력 평균으로 `score_value` 를 다시 매기는데, 이를 코드 상수로 두면 과거 응답이 어떤 배점으로
계산됐는지 추적할 수 없다. 새 배점은 새 `survey_templates.version` 으로 추가하고, 과거 응답은 자기
버전의 배점을 그대로 유지한다.

응답 단위가 users 인 이유 (스펙과 다른 점): 스펙 2절은 `survey_responses.player_id` 를 제안하지만,
설계서 흐름 A(5.3절)는 **회원가입 직후, 팀에 들어가기 전에** 설문을 받는다. 그 시점에는 `players`
행이 없으므로 응답은 계정(`users`)에 묶고, 팀에 가입할 때마다 그 응답을 클럽 내 z-score 로 표준화해
그 팀의 `player_profiles.prior_overall` 로 변환한다 (같은 응답 → 팀마다 다른 prior).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, CreatedAtMixin
from app.models.enums import AnswerType, db_enum


class SurveyTemplate(CreatedAtMixin, Base):
    """설문 한 버전. `GET /surveys/onboarding` 은 is_active 인 템플릿의 문항을 내려준다.

    동시에 하나만 활성인 것을 전제로 하지만 DB 제약으로 강제하지는 않는다 (관리자가 전환).
    기존 버전은 응답이 참조하므로 삭제하지 않고 is_active 만 내린다.
    v1 시드는 `alembic/versions/0002_*.py` 가 `app/db/survey_seed.py` 를 불러 넣는다.
    """

    __tablename__ = "survey_templates"

    id: Mapped[BigPK]
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)  # 1, 2, 3 … 단조 증가
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # 예: "온보딩 v1"
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    # 화면 표시 순서(display_order)대로 로드
    questions: Mapped[list["SurveyQuestion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="SurveyQuestion.display_order"
    )


class SurveyQuestion(Base):
    """문항 하나. 8.3절의 14문항(A1~E3)이 각각 한 행이다. D3 는 두 줄이라 D3A / D3B 두 행으로 나눈다.

    `code` 는 버전이 바뀌어도 같은 의미의 문항을 잇는 열쇠다 (prior 변환식이 code 로 문항을 찾는다).
    """

    __tablename__ = "survey_questions"
    # 한 템플릿 안에서 문항 코드는 유일. 버전이 다르면 같은 code 가 다시 존재한다
    __table_args__ = (UniqueConstraint("template_id", "code", name="uq_survey_questions_code"),)

    id: Mapped[BigPK]
    template_id: Mapped[int] = mapped_column(
        ForeignKey("survey_templates.id", ondelete="CASCADE"), nullable=False
    )
    section: Mapped[str] = mapped_column(String(1), nullable=False)  # A 기본 / B 공격 / C 수비 / D 포지션 / E 성향
    code: Mapped[str] = mapped_column(String(10), nullable=False)  # A1 … E3, D3A/D3B
    question_text: Mapped[str] = mapped_column(Text, nullable=False)  # 문항 본문
    answer_type: Mapped[AnswerType] = mapped_column(db_enum(AnswerType, 15), nullable=False)  # 척도 종류 (6종)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 화면 표시 순서
    # prior 계산에 쓰이는 문항의 비중 (스펙 5절). 참고용 — 실제 계산은 survey_service.PRIOR_COMPONENTS 가 정한다
    prior_weight: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    help_text: Mapped[str | None] = mapped_column(Text)  # 문항 아래 보조 설명 (선택)
    group_label: Mapped[str | None] = mapped_column(String(50))  # TRIO 처럼 한 화면에 묶어 보여줄 문항의 공통 제목

    template: Mapped[SurveyTemplate] = relationship(back_populates="questions")
    # STEPPER 문항은 options 가 비어 있다
    options: Mapped[list["SurveyOption"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="SurveyOption.option_order"
    )


class SurveyOption(Base):
    """문항의 선택지 하나 (앵커 문구, 칩, 서열 항목).

    `score_value` 가 prior 계산에 들어가는 값이다. 처음에는 서열대로 0/1/2/3(4단계) 또는 0~4(5택)로
    두고, 8.6절 재보정 때 실측값으로 바뀐다. 재보정은 이 행을 고치지 않고 새 템플릿 버전에 새 행을 만든다.
    `code` 는 스펙에 없지만 B1 의 "픽앤롤 핸들러" 처럼 특정 선택지를 6축 세부 점수에 매핑하는 데 필요하다.
    """

    __tablename__ = "survey_options"
    # 한 문항 안에서 선택지 코드는 유일
    __table_args__ = (UniqueConstraint("question_id", "code", name="uq_survey_options_code"),)

    id: Mapped[BigPK]
    question_id: Mapped[int] = mapped_column(
        ForeignKey("survey_questions.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)  # 예: B1 의 "PNR_HANDLER", D1 의 "PG"
    option_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 표시 순서. 앵커는 순서가 곧 등급
    label: Mapped[str] = mapped_column(Text, nullable=False)  # 화면 문구 (행동 앵커 문장 등)
    score_value: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)  # 초기 균등 배점, 재보정 대상

    question: Mapped[SurveyQuestion] = relationship(back_populates="options")


class SurveyResponse(Base):
    """한 사용자의 설문 제출 1건. **1인 1회** (UNIQUE user_id) — 재제출은 409 ALREADY_SUBMITTED.

    제출되면 `users.onboarding_completed` 가 true 로 바뀌고 (FR-03), 소속된 모든 팀의 prior 가
    다시 계산된다. 수정은 관리자 보정으로만 한다 (스펙 1절).
    """

    __tablename__ = "survey_responses"
    __table_args__ = (UniqueConstraint("user_id", name="uq_survey_responses_user"),)

    id: Mapped[BigPK]
    template_id: Mapped[int] = mapped_column(ForeignKey("survey_templates.id"), nullable=False)  # 응답한 버전
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    answers: Mapped[list["SurveyAnswer"]] = relationship(
        back_populates="response", cascade="all, delete-orphan"
    )


class SurveyAnswer(Base):
    """문항별 응답. 문항당 정확히 1행 (UNIQUE response_id, question_id).

    - 선택형 (ANCHOR_4 / MULTI_CHIP / ORDINAL_5 / SINGLE_CHOICE / TRIO): `selected_option_ids` 에
      survey_options.id 배열. 단일선택도 길이 1 배열로 통일한다.
    - STEPPER (A1 키): `numeric_value` 에 cm 값, `selected_option_ids` 는 빈 배열.
    """

    __tablename__ = "survey_answers"
    __table_args__ = (UniqueConstraint("response_id", "question_id", name="uq_survey_answers_question"),)

    id: Mapped[BigPK]
    response_id: Mapped[int] = mapped_column(
        ForeignKey("survey_responses.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("survey_questions.id"), nullable=False, index=True)
    selected_option_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))

    response: Mapped[SurveyResponse] = relationship(back_populates="answers")
