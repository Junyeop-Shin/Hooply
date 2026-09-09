"""온보딩 설문 · 포지션 스키마 — 7.3절 "온보딩 설문" 엔드포인트의 요청/응답 (F1, S-03, 8장,
설문 설계).

대상 엔드포인트: GET /surveys/onboarding (문항 조회), POST /surveys/onboarding/responses (제출),
GET /me/profile, PUT /me/positions.

설문은 `survey_templates` 로 버전 관리된다 (8.6절 앵커 재보정 시 배점이 바뀌므로). 문항·선택지는
DB 에서 내려주고 프론트는 `answer_type` 에 따라 위젯을 고른다 (스펙 3절 척도 6종).
응답은 스펙 5절 규칙으로 z-score 가중합되어 소속 팀별 사전 실력값(`player_profiles.prior_overall`)이 된다.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import AnswerType, Position, SelfRankLevel
from app.schemas.common import ORMModel, SkillGrade


class SurveyOptionView(ORMModel):
    """문항의 선택지 하나 (`survey_options` 행). `SurveyQuestionView.options` 원소."""

    id: int = Field(description="survey_options.id. 응답 시 selected_option_ids 에 넣는 값")
    code: str = Field(description="선택지 식별 코드 (예: PNR_HANDLER). 6축 매핑·앵커 재보정 추적 키")
    option_order: int = Field(description="표시 순서. 앵커·서열 문항에서는 순서가 곧 등급")
    label: str = Field(description="화면에 보이는 문구")


class SurveyQuestionView(ORMModel):
    """문항 하나 (`survey_questions` 행). `SurveyTemplateView.questions` 원소."""

    id: int = Field(description="survey_questions.id. 응답 시 question_id 에 넣는 값")
    section: str = Field(description="A 기본 / B 공격 / C 수비 / D 포지션 / E 성향·상대평가")
    code: str = Field(description="문항 번호 (A1 … E3). D3 는 D3A(1번)·D3B(5번) 두 행")
    question_text: str
    answer_type: AnswerType = Field(
        description="STEPPER(숫자) / ANCHOR_4(4단계 앵커) / MULTI_CHIP(다중선택) / ORDINAL_5(5택 서열) / "
        "SINGLE_CHOICE(단일선택) / TRIO(가능+선호·가능·불가)"
    )
    display_order: int
    help_text: str | None = None
    group_label: str | None = Field(default=None, description="같은 값의 문항은 한 화면에 묶어 보여준다 (D3A/D3B)")
    options: list[SurveyOptionView] = Field(default=[], description="option_order 순. STEPPER 는 비어 있다")


class SurveyTemplateView(BaseModel):
    """활성 설문 전체 — `GET /surveys/onboarding` 응답 (S-03)."""

    template_id: int = Field(description="survey_templates.id. 제출 시 함께 보내면 버전 불일치를 검사한다")
    version: int
    name: str
    questions: list[SurveyQuestionView] = Field(description="display_order 순. 15행 (14문항, D3 는 2행)")


class SurveyAnswerIn(BaseModel):
    """문항 1개에 대한 응답. 유형에 따라 둘 중 하나만 채운다 (둘 다 비면 400)."""

    question_id: int
    selected_option_ids: list[int] = Field(
        default=[], description="선택형 문항. MULTI_CHIP 은 1개 이상, 그 외는 정확히 1개"
    )
    numeric_value: Decimal | None = Field(default=None, description="STEPPER(A1 키 cm) 전용")


class SurveyResponseIn(BaseModel):
    """설문 제출 — `POST /surveys/onboarding/responses` (로그인 사용자, FR-03).

    15문항 전부 필수. 이미 제출했으면 409 ALREADY_SUBMITTED (1인 1회).
    """

    template_id: int | None = Field(default=None, description="생략 가능. 보내면 활성 템플릿과 일치해야 한다")
    answers: list[SurveyAnswerIn] = Field(min_length=1)


class TeamProfileSummary(BaseModel):
    """소속 팀 하나에서의 내 실력 요약. 수치는 없고 등급만 (FR-28)."""

    team_id: int
    team_name: str
    player_id: int
    skill_grade: SkillGrade | None = Field(default=None, description="항상 None — 등급은 본인도 볼 수 없다 (매니저 전용). 필드는 호환용")
    prior_source: str | None = Field(default=None, description="SURVEY / MANAGER / DEFAULT / None")
    skill_confidence: Decimal | None = None
    self_rank_level: SelfRankLevel | None = Field(default=None, description="이 팀에서 답한 내 실력 위치. None 이면 아직 안 물어봄")
    survey_sample_size: int = Field(default=0, description="이 팀에서 설문에 응답한 회원 수. 5명 미만이면 z-score 를 계산하지 않는다")
    quarters_played: int = Field(default=0, description="이 팀에서 출전한 쿼터 수 (표시용)")


class MyProfile(BaseModel):
    """내 실력·포지션 프로필 — `GET /me/profile` 과 설문 제출(201) 응답 (S-17, S-03 완료 화면)."""

    onboarding_completed: bool
    survey_submitted_at: datetime | None = None
    height_cm: int | None = None
    primary_position: Position | None = None
    playable_positions: list[Position] = []
    teams: list[TeamProfileSummary] = Field(default=[], description="소속 팀별 등급. 팀이 없으면 빈 배열")


class SelfRankIn(BaseModel):
    """팀 가입 후 "이 동호회에서 본인의 실력 위치" — `PUT /teams/{team_id}/self-rank` (팀원 본인).

    구 설문 E3. 팀을 알아야 답할 수 있으므로 온보딩 설문이 아니라 팀 가입 직후에 묻는다.
    prior 계산에서 가중치 0.30 (가장 큰 성분).
    """

    level: SelfRankLevel = Field(description="TOP10 / TOP30 / MID / BOT30 / BOT10")


class PositionIn(BaseModel):
    """포지션 1개에 대한 설정. `PositionsUpdate.positions` 원소 (`player_positions` 행 1개)."""

    position: Position = Field(description="PG / SG / SF / PF / C")
    can_play: bool = Field(default=True, description="수행 가능 여부 (D1). 1번·5번 가능자는 배정의 하드 제약 자원이 된다")
    preference_rank: int | None = Field(default=None, ge=1, le=5, description="선호 순위. 1이 가장 선호 (D2)")
    self_rating: int | None = Field(default=None, ge=1, le=5, description="그 포지션에서의 자기 평가 1~5 (참고용)")


class PositionsUpdate(BaseModel):
    """가능/선호 포지션 수정 — `PUT /me/positions`. 소속된 모든 팀의 players 행에 같은 값을 적용한다."""

    positions: list[PositionIn] = Field(max_length=5, description="포지션 중복 불가. 빠진 포지션은 삭제된다")
