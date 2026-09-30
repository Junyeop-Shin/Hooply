"""7.2절 공통 스키마 — OpenAPI에서 $ref로 재사용된다.

특정 엔드포인트 전용이 아니라 여러 응답에 끼워 넣어 쓰는 조각들이다.

- 목록 껍데기: `Page[T]` = `{items, meta}`, `ItemList[T]` = `{items}` (7.1절 목록 응답 규약)
- 사람 카드:   `UserSummary` → `PlayerCard` → `PlayerCardDetailed`
               (뒤로 갈수록 노출 정보가 많다. 어디까지 보여줄지는 호출자의 역할로 정한다)
- 팀 뷰:       `SquadView` (배정 결과의 팀 하나)
- `Position` / `Strategy` 는 `app.models.enums` 의 것을 그대로 재노출한다. 설계서의
  PositionEnum / StrategyEnum 에 해당하며, 다른 스키마 모듈이 여기서 import 할 수 있게 둔 것.

노출 원칙 (3.3절 권한 매트릭스, FR-28): 플레이어에게는 실력 **수치**를 보여주지 않고 5등급만
보여준다. 수치 필드는 `PlayerCardDetailed` 에만 있고 MANAGER / ADMIN 에게만 내려간다.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Position, Strategy  # noqa: F401 — PositionEnum / StrategyEnum 재노출


class ORMModel(BaseModel):
    """SQLAlchemy 모델 인스턴스를 그대로 넘겨 만들 수 있는 응답 베이스.

    `from_attributes=True` 덕분에 `TeamDetail.model_validate(team_row)` 처럼 dict 가 아닌
    객체의 속성에서 값을 읽는다. DB 행을 응답으로 바꾸는 `...View` / `...Detail` 모델이 상속한다.
    요청(입력) 모델은 굳이 이걸 상속할 필요가 없다.
    """

    model_config = ConfigDict(from_attributes=True)


class PageMeta(BaseModel):
    """페이징 목록의 메타 정보 (7.2절 PageMeta). `Page[T].meta` 에 들어간다."""

    page: int = Field(description="현재 페이지 번호. 1부터 시작")
    size: int = Field(description="페이지당 항목 수 (요청의 ?size=)")
    total: int = Field(description="조건에 맞는 전체 항목 수")
    has_next: bool = Field(description="다음 페이지가 있는지. 프론트의 '더 보기' 판단용")


class Page[T](BaseModel):
    """페이징 목록 응답 `{items, meta}` (7.1절 규약).

    항목이 많아질 수 있는 목록에 쓴다: GET /teams/{id}/events, GET /admin/users, GET /admin/audit-logs.
    `T` 에 항목 스키마를 넣으면 OpenAPI 에 `Page_EventView_` 같은 이름으로 생성된다.
    """

    items: list[T]
    meta: PageMeta


class ItemList[T](BaseModel):
    """페이징 없는 목록 응답 `{items}`.

    한 번에 전부 내려도 되는 작은 목록에 쓴다: 팀원, 게스트 검색, 쿼터, 배정 실행 이력 등.
    나중에 페이징이 필요해지면 `Page[T]` 로 바꾸면 되고, 프론트는 `items` 만 보므로 호환된다.
    """

    items: list[T]


class SkillGrade(StrEnum):
    """플레이어에게는 수치 대신 5등급만 노출한다 (FR-28).

    A 가 가장 높다. 변환은 `app/services/player_service.py:grade_of` — **같은 팀 활동 회원 안에서의 위치**
    (상위 10% A · 20% B · 40% C · 20% D · 하위 10% E, 회원 5명 미만이면 절대 구간). 등급은 일정 단위로 바뀐다
    — 경기 기록을 저장할 때 실력을 다시 계산하므로 (9.2절 표시 정책).
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class UserSummary(ORMModel):
    """로그인 계정(users)의 최소 표시 정보 (7.2절 UserSummary).

    "누구인지"만 보여주면 되는 자리에 쓴다 — 예: `TeamDetail.owner`. 실력 정보가 없다.
    참가자(players) 기준 정보가 필요하면 `PlayerCard` 를 쓴다.
    """

    id: int = Field(description="users.id")
    name: str
    nickname: str | None = None
    profile_image_url: str | None = Field(
        default=None,
        description="카카오 프로필 이미지 등. CDN URL은 만료될 수 있으므로 프론트는 이니셜 아바타 폴백을 둔다 (11.5절)",
    )


class PlayerCard(ORMModel):
    """UserSummary + 실력 등급·포지션·참여율. 게스트는 user_id가 None.

    **참가자(players) 한 명의 카드** (7.2절 PlayerCard). 계정이 아니라 players 행 기준이므로
    게스트도 같은 형태로 표현된다. 사용처: 팀원 목록(PLAYER 시점), 참석자 현황, 배정 결과의 팀원,
    게스트 등록/검색 응답, 피어 설문 대상 목록, 온보딩 설문 제출 응답 등.

    실력은 **등급(`skill_grade`)만** 있고 수치는 없다. 누구에게 보여줘도 되는 안전한 뷰다.
    변환은 `player_service.to_card`.
    """

    id: int = Field(description="player_id (users.id가 아님). 같은 사람이 두 팀에 있으면 팀마다 값이 다르다 (13.2절 4항)")
    user_id: int | None = Field(default=None, description="회원이면 users.id, 게스트면 None")
    kind: str = Field(description="MEMBER(회원) / GUEST(계정 없는 게스트)")
    display_name: str = Field(description="표시 이름. 게스트는 매니저가 입력한 이름")
    role: str = Field(description="이 팀에서의 역할. MANAGER / PLAYER (게스트는 항상 PLAYER)")
    profile_image_url: str | None = None
    height_cm: int | None = Field(default=None, description="키(cm). 회원은 users.height_cm, 게스트는 players.height_cm")
    skill_grade: SkillGrade | None = Field(
        default=None,
        description="5등급 A~E. skill_overall이 있으면 그것, 없으면 사전값(prior_overall)으로 계산. 프로필이 없으면 None",
    )
    primary_position: Position | None = Field(
        default=None, description="가장 선호하는 포지션 (preference_rank가 가장 앞선 것). 없으면 None"
    )
    playable_positions: list[Position] = Field(default=[], description="수행 가능한 포지션 목록 (can_play=True)")
    attendance_rate: float | None = Field(default=None, description="참여율 0~1. 아직 계산하지 않으며 None으로 내려간다")
    skill_confidence: Decimal | None = Field(default=None, description="0~1. 게스트·신규는 0.3 미만")


class PlayerCardDetailed(PlayerCard):
    """MANAGER / ADMIN 전용 — 수치 포함.

    `GET /teams/{id}/players` 에서 호출자가 MANAGER 면 이 모델, PLAYER 면 `PlayerCard` 로 내려간다
    (13.1절 Q3: 매니저는 결과를 판단해야 하므로 수치까지 열람). 플레이어에게 이 모델을 직렬화해
    보내면 안 된다. 변환은 `player_service.to_card_detailed`.
    """

    skill_overall: Decimal | None = Field(
        default=None,
        description="현재 종합 실력. 단위는 '쿼터당 득실 기여(점)' — +2.0이면 이 선수가 코트에 있을 때 팀이 쿼터당 2점 유리 (9.2절)",
    )
    prior_overall: Decimal | None = Field(
        default=None, description="사전 실력값. 설문 + 매니저 정렬, 게스트는 매니저 지정 등급에서 온다 (8.4절·8.5절)"
    )
    skill_axes: dict[str, Decimal | None] = Field(
        default={},
        description="세부 6축: shooting / ball_handling / passing / defense / rebound_post / stamina",
    )
    avg_margin: Decimal | None = Field(
        default=None,
        description="쿼터당 평균 코트 마진(시간 정규화). 표시용 파생값이며 실력 지표 자체는 아니다 (9.1절)",
    )
    quarters_played: int = Field(default=0, description="누적 출전 쿼터 수. 신뢰도의 근거")
    attended_events: int = Field(default=0, description="참석(ATTEND)한 지난 회차 수. 팀원 관리 화면의 참여 횟수 정렬·표시용")


class SquadView(BaseModel):
    """배정 결과의 팀 하나 (7.2절 SquadView). `CandidateView.squads`, `AdoptedAssignment.squads` 원소."""

    squad_no: int = Field(description="팀 번호. 1부터. PIN 제약의 squad_no와 같은 번호 체계")
    squad_name: str = Field(description="팀 이름. 기본값 블랙 / 화이트 (13.1절 Q6)")
    avg_skill: Decimal | None = None  # 플레이어 뷰에서는 마스킹(None)
    members: list[PlayerCard] = Field(description="팀원 카드 목록. 게스트 포함")
    assigned_positions: dict[int, Position | None] = Field(
        default={}, description="player_id → 배정 포지션. 슬롯을 못 채운 사람은 주 포지션 또는 None"
    )
    manual_override_ids: list[int] = Field(default=[], description="매니저가 직접 교체한 선수 (F7)")
    avg_height_cm: float | None = Field(default=None, description="팀원 평균 신장 (키를 입력한 회원·게스트 기준). 없으면 None")
