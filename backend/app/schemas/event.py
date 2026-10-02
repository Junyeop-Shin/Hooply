"""일정 · 참석 스키마 — 7.3절 "일정 · 참석" 엔드포인트의 요청/응답 (F4, S-09 ~ S-11).

대상 엔드포인트: POST|GET /teams/{id}/events, GET|PATCH|DELETE /events/{id},
PUT /events/{id}/attendance (본인 응답), PUT /events/{id}/attendances/{player_id} (매니저 대리 응답),
GET /events/{id}/attendances (참석 현황 + 포지션 분포 요약).

참석 응답은 `event_attendances` 행이며 `player_id` 기준이다. 게스트는 로그인할 수 없으므로
매니저가 `attendances/{player_id}` 로 대신 등록한다 (3.3절 권한 매트릭스 "△ 매니저가 대신 등록").
"""

from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AttendanceStatus, Position
from app.schemas.common import ORMModel, PlayerCard


class EventCreate(BaseModel):
    """일정 등록 요청 — `POST /teams/{id}/events` (MANAGER 전용, S-09, FR-08).

    팀이 PENDING(5명 미만)이면 422 TEAM_NOT_ACTIVE. 날짜만 필수이고 나머지는 나중에 채워도 된다.
    """

    title: str | None = Field(default=None, max_length=100, description="비우면 프론트가 날짜로 표시")
    event_date: date = Field(description="모임 날짜")
    start_time: time | None = None
    end_time: time | None = None
    venue: str | None = Field(default=None, max_length=100, description="장소. 팀의 home_court와 다를 수 있다")
    rsvp_deadline: datetime | None = Field(
        default=None, description="참석 응답 마감 시각. 지나면 본인 응답은 422 RSVP_CLOSED (매니저 대리 응답은 가능)"
    )
    memo: str | None = Field(default=None, max_length=1000, description="공지 메모 (회비, 준비물 등). 1000자까지")

    @field_validator("rsvp_deadline")
    @classmethod
    def _aware_deadline(cls, v: datetime | None) -> datetime | None:
        """시간대 없는 값("2026-09-14T18:00")은 서비스 시간대(Asia/Seoul)로 해석한다. naive 로 두면 UTC 비교에서 500 이 난다."""
        if v is not None and v.tzinfo is None:
            from zoneinfo import ZoneInfo

            from app.core.config import get_settings

            return v.replace(tzinfo=ZoneInfo(get_settings().timezone))
        return v


class EventUpdate(EventCreate):
    """일정 수정 — `PATCH /events/{id}` (MANAGER 전용). 모든 필드가 선택이며 None 은 '변경 없음'."""

    event_date: date | None = None


class EventView(ORMModel):
    """일정 하나 — `GET /events/{id}`, 목록의 items, 등록/수정 응답 (S-04 홈 카드, S-10 일정 상세).

    `my_attendance` 는 호출자 기준이라 같은 일정도 사람마다 다르게 내려간다.
    """

    id: int
    team_id: int
    title: str | None
    event_date: date
    start_time: time | None
    end_time: time | None
    venue: str | None
    rsvp_deadline: datetime | None
    status: str = Field(description="OPEN(응답 받는 중) / CLOSED(마감) / DONE(경기 끝) / CANCELED")
    memo: str | None
    attend_count: int = Field(default=0, description="현재 ATTEND 응답 수 (게스트 포함)")
    my_attendance: AttendanceStatus | None = Field(
        default=None, description="호출자의 응답. 아직 안 했으면 PENDING, 이 팀 참가자가 아니면 None"
    )
    rsvp_open: bool = Field(default=True, description="지금 본인 응답이 가능한지 (OPEN 상태이고 마감 전)")
    my_role: str | None = Field(default=None, description="호출자의 이 팀 역할 (MANAGER / PLAYER)")
    adopted_candidate_id: int | None = Field(default=None, description="확정된 배정안이 있으면 그 id (S-14 진입점)")
    run_count: int = Field(default=0, description="이 회차의 배정 실행 횟수")
    quarter_count: int = Field(default=0, description="기록된 쿼터 수. 0 이면 아직 기록 전")
    my_squad_name: str | None = Field(default=None, description="확정된 배정에서 내 팀 이름 (없으면 None)")
    my_assigned_position: str | None = Field(default=None, description="확정된 배정에서 내 포지션")
    survey_open: bool = Field(default=False, description="피어 투표가 열렸는지 (일정 종료 시각 경과)")
    my_survey_submitted: bool = Field(default=False, description="호출자가 이 회차 피어 투표를 제출했는지")
    survey_responded: int = Field(default=0, description="피어 투표 제출 수")
    survey_total: int = Field(default=0, description="투표 대상 인원 = 참석한 회원 수 (게스트 제외)")


class AttendanceUpdate(BaseModel):
    """참석 응답 요청 (S-10, FR-09).

    - `PUT /events/{id}/attendance` — 본인 응답. 마감 전까지 몇 번이든 바꿀 수 있다.
    - `PUT /events/{id}/attendances/{player_id}` — 매니저가 대신 응답. 게스트 참석 등록이 주 용도.
    """

    status: AttendanceStatus = Field(description="ATTEND / ABSENT / PENDING(응답 취소)")
    note: str | None = Field(default=None, max_length=200, description="'늦게 감' 같은 짧은 메모 (200자까지)")


class AttendanceView(BaseModel):
    """참석 응답 한 건 — 위 PUT 두 개의 응답이자 `AttendanceList.items` 원소."""

    player: PlayerCard
    status: AttendanceStatus
    note: str | None = None
    responded_at: datetime | None = Field(default=None, description="마지막으로 응답을 바꾼 시각. 미응답이면 None")
    registered_by: int | None = Field(
        default=None, description="대신 등록한 사람의 users.id (게스트 등록자 / 대리 응답 매니저). 본인 응답이면 None"
    )
    registered_by_name: str | None = Field(default=None, description="registered_by 의 표시 이름")
    team_lock_request_player_id: int | None = Field(
        default=None, description="게스트 행 전용. '이 player 와 같은 팀으로' 요청 (게스트 기능 설계)"
    )
    team_lock_request_player_name: str | None = None
    can_edit: bool = Field(default=False, description="호출자가 이 게스트 등록을 수정·삭제할 수 있는지 (등록자 본인 또는 매니저)")


class AttendanceSummary(BaseModel):
    """참석 현황 요약 — S-11 상단의 '포지션 분포 요약 바'와 '빅맨·핸들러 경고' 데이터 (FR-15, FR-34).

    ATTEND 응답자만 집계한다. `position_counts` 는 사람당 **가장 선호하는 포지션 하나**만 세므로
    합이 참석 인원 이하다 (선호를 안 정한 사람은 어디에도 안 들어간다). 핸들러·빅맨 수는 '가능' 기준.
    """

    attend: int = Field(description="참석 응답 수 (게스트 포함)")
    absent: int = Field(description="불참 응답 수")
    pending: int = Field(description="미응답 수")
    guest_count: int = Field(default=0, description="참석 게스트 수")
    position_counts: dict[Position, int] = Field(description="포지션별 인원 — 사람당 가장 선호하는 포지션 하나만 (참석자 중)")
    handler_count: int = Field(description="1번(PG) 가능자 수")
    bigman_count: int = Field(description="4·5번(PF/C) 가능자 수")
    warnings: list[str] = Field(default=[], description="FR-34: 빅맨·핸들러 부족 경고 (차단 아님)")


class AttendanceList(BaseModel):
    """`GET /events/{id}/attendances` 응답 — 응답 목록 + 요약 (S-11 참석/불참/미응답 3열)."""

    items: list[AttendanceView] = Field(description="?status= 로 걸렀다면 그 상태만")
    summary: AttendanceSummary
    my_player_id: int | None = Field(default=None, description="호출자의 이 팀 players.id")


# --- 회차별 게스트 등록 (게스트 기능 설계) ---


class EventGuestCreate(BaseModel):
    """회차에 게스트 등록 — `POST /events/{id}/guests` (팀원 누구나).

    `existing_player_id` 를 주면 재방문 게스트의 기존 레코드를 재사용해 참석만 추가한다 (FR-12).
    없으면 이름으로 새 게스트를 만들되, 같은 이름의 게스트가 있고 `force_new=false` 면
    200 + `GuestSimilar` 로 확인을 요청한다.
    """

    display_name: str = Field(min_length=1, max_length=50)
    skill_grade: int | None = Field(default=None, ge=1, le=5, description="미지정 시 클럽 평균")
    height_cm: int | None = Field(default=None, ge=120, le=250, description="게스트 키(cm). 팀 평균 신장 계산에 쓰인다")
    preferred_position: Position | None = None
    playable_positions: list[Position] = []
    team_lock_request: bool = Field(default=False, description="true 면 등록자 본인과 같은 팀 배정을 요청 (FR-11a)")
    existing_player_id: int | None = Field(default=None, description="재방문 게스트의 players.id")
    force_new: bool = Field(default=False, description="동명이인이 있어도 새 게스트로 추가")


class EventGuestUpdate(BaseModel):
    """회차 게스트 등록 수정 — `PATCH /events/{id}/guests/{player_id}` (등록자 본인 또는 MANAGER)."""

    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    skill_grade: int | None = Field(default=None, ge=1, le=5)
    height_cm: int | None = Field(default=None, ge=120, le=250, description="게스트 키(cm). 필드를 빼면 그대로, null 을 보내면 지운다")
    preferred_position: Position | None = None
    playable_positions: list[Position] | None = None
    team_lock_request: bool | None = Field(default=None, description="None 이면 변경 없음")
    status: AttendanceStatus | None = Field(default=None, description="참석/불참 변경. None 이면 유지")


class LockSuggestion(BaseModel):
    """묶기 제안 한 건 — `GET /events/{id}/assignment/suggestions` (MANAGER, S-12).

    게스트 등록자가 요청한 "같은 팀" 희망. 대상이 그 회차에 참석(ATTEND)인 경우만 내려간다.
    매니저가 승인하면 배정 실행 시 `lock_groups` 에 넣는다.
    """

    guest: PlayerCard
    target: PlayerCard = Field(description="같은 팀을 요청한 상대 (보통 등록자 본인)")
    requested_by_user_id: int | None = None


class GuestPresetView(BaseModel):
    """이전에 초대한 게스트 — `GET /events/{id}/guests/presets` (내가 등록했던 것만, 최근 사용순).

    선택하면 이름·실력·선호/가능 포지션·같은 팀 요청이 폼에 채워지고, `existing_player_id` 로 기록을 이어 붙인다.
    """

    id: int
    display_name: str
    skill_grade: int | None = None
    height_cm: int | None = None
    preferred_position: Position | None = None
    playable_positions: list[Position] = []
    team_lock_request: bool = False
    existing_player_id: int | None = Field(default=None, description="재사용할 게스트 players.id (레코드가 남아 있으면)")
    use_count: int = 1
    last_used_at: datetime
