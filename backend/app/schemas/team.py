"""팀 · 게스트 · 매니저 실력 정렬 스키마 — 7.3절 "팀 · 참가자", "게스트 관리(F13)",
"매니저 실력 정렬(F14)" 엔드포인트의 요청/응답.

대상 엔드포인트:
- 팀:     POST /teams, POST /teams/join, GET|PATCH /teams/{id}, POST /teams/{id}/code:regenerate,
          PATCH /teams/{id}/players/{pid}/role
- 게스트: POST|GET /teams/{id}/guests, PATCH /players/{id}, POST /players/{id}:merge|:unmerge
- 정렬:   GET /teams/{id}/rankings/latest, POST|GET /teams/{id}/rankings

핵심 전제 (6.2절): 로그인 계정(`users`)과 참가자(`players`)는 분리되어 있고, 팀 소속·역할·게스트는
모두 `players` 행이다. 그래서 게스트 관련 응답도 회원과 같은 `PlayerCard` 로 내려간다.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import Position, TeamRole
from app.schemas.common import ORMModel, PlayerCard, UserSummary

MAX_RANKING_PLAYERS = 100  # 정렬 한 번에 올릴 수 있는 인원 (요청 크기 상한)


class TeamCreate(BaseModel):
    """팀 생성 요청 — `POST /teams` (S-05, FR-04). 생성자는 자동으로 MANAGER 가 된다."""

    name: str = Field(min_length=1, max_length=50, description="팀명")
    description: str | None = Field(default=None, max_length=500, description="팀 소개 (500자까지)")
    home_court: str | None = Field(default=None, max_length=100, description="주로 모이는 체육관")


class TeamCreated(BaseModel):
    """`POST /teams` 의 201 응답. 프론트는 `team_code` 를 카카오톡 공유 화면에 띄운다."""

    id: int = Field(description="teams.id")
    team_code: str = Field(description="8자 초대 코드 (대문자+숫자, 0/O/1/I 제외)")


class TeamJoinRequest(BaseModel):
    """팀 코드로 가입 — `POST /teams/join` (S-06, FR-05).

    성공 시 `TeamDetail`. 코드가 없거나 재발급으로 만료됐으면 404 TEAM_CODE_NOT_FOUND,
    이미 소속이면 409 ALREADY_MEMBER.
    """

    team_code: str = Field(min_length=8, max_length=8, description="정확히 8자")


class TeamUpdate(BaseModel):
    """팀 정보 수정 — `PATCH /teams/{id}` (MANAGER 전용). 보낸 필드만 바꾼다."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    home_court: str | None = Field(default=None, max_length=100)


class TeamDetail(ORMModel):
    """팀 상세 — `GET /teams/{id}`, `POST /teams/join`, `PATCH /teams/{id}` 응답 (S-07).

    소속 팀원(또는 ADMIN)만 볼 수 있다. `my_*` 필드는 호출자 기준으로 채워진다.
    """

    id: int
    name: str
    description: str | None
    team_code: str
    status: str = Field(description="PENDING(5명 미만 또는 승인 전, 일정 기능 잠김) / ACTIVE / ARCHIVED")
    approval_status: str = Field(default="APPROVED", description="관리자 승인: PENDING / APPROVED / REJECTED")
    min_members: int = Field(description="활성화에 필요한 최소 인원. 기본 5 (FR-06)")
    home_court: str | None
    owner: UserSummary = Field(description="팀을 만든 계정 (teams.owner_user_id)")
    member_count: int = Field(description="현재 활성 참가자 수 (게스트 포함)")
    my_role: TeamRole | None = Field(default=None, description="호출자의 이 팀 역할. 비소속 ADMIN이 조회하면 None")
    my_player_id: int | None = Field(default=None, description="호출자의 이 팀 players.id. 비소속 ADMIN이면 None")
    created_at: datetime


class TeamCodeView(BaseModel):
    """`POST /teams/{id}/code:regenerate` 응답. 이전 코드는 즉시 무효가 된다."""

    team_code: str


class RoleUpdate(BaseModel):
    """팀원 역할 변경 — `PATCH /teams/{id}/players/{pid}/role` (MANAGER 전용, FR-07).

    마지막 매니저를 PLAYER 로 내리면 422 CANNOT_DEMOTE_LAST_MANAGER.
    게스트에게 MANAGER 를 주는 것은 400 VALIDATION_ERROR (게스트는 로그인할 수 없으므로).
    """

    role: TeamRole = Field(description="MANAGER(부여) / PLAYER(회수)")


# --- 게스트 (F13) ---


class GuestCreate(BaseModel):
    """게스트 등록 요청 — `POST /teams/{id}/guests` (팀원 누구나, S-11, FR-10~12 · 게스트 기능 설계).

    계정 없는 사람을 이름만으로 `players(kind=GUEST)` 행으로 만든다. 동명이인 게스트가 이미 있으면
    201 대신 200 + `GuestSimilar` 를 돌려주고, 등록자가 기존 레코드를 고르거나 `force_new=true` 로
    다시 보낸다 (5.4절 "게스트 동명이인").
    """

    display_name: str = Field(min_length=1, max_length=50, description="게스트 이름. 연락처 등 다른 개인정보는 받지 않는다 (10장)")
    skill_grade: int | None = Field(
        default=None, ge=1, le=5,
        description="미지정 시 클럽 평균값. 지정하면 클럽 내 분위수로 환산해 prior_overall이 되고 skill_confidence=0.25, "
        "미지정이면 클럽 평균 + skill_confidence=0 으로 '데이터 없음' 처리 (9.5절)",
    )
    height_cm: int | None = Field(default=None, ge=120, le=250, description="게스트 키(cm). 팀 평균 신장 계산에 쓰인다")
    preferred_position: Position | None = Field(default=None, description="선호 포지션 (단일). 스펙 FR-11")
    playable_positions: list[Position] = Field(default=[], description="등록자가 아는 범위의 가능 포지션. 비워도 된다")
    force_new: bool = Field(default=False, description="동명이인이 있어도 새 게스트로 추가")


class MergeCandidate(BaseModel):
    """이름이 같은 게스트–회원 쌍 — `GET /teams/{id}/guests/merge-candidates` (MANAGER).

    "게스트로 자주 오다가 회원가입한 사람" 을 찾아 주는 힌트다. 이름 일치는 동명이인일 수 있으므로
    자동 병합하지 않고 매니저가 확인 후 `:merge` 를 호출한다.
    """

    guest: PlayerCard
    member: PlayerCard


class GuestSimilar(BaseModel):
    """동명이인 후보가 있으면 201 대신 200으로 이 목록을 돌려주고 확인을 요청한다.

    프론트(S-11)는 이 목록을 먼저 보여주고 "새 게스트로 추가" 선택지를 아래에 둔다.
    기존 레코드를 고르면 그 player_id 로 참석 등록(`PUT /events/{id}/attendances/{pid}`)만 하면 된다.
    """

    similar: list[PlayerCard] = Field(description="같은/비슷한 이름의 기존 게스트 카드")


class PlayerUpdate(BaseModel):
    """게스트 정보 수정 — `PATCH /players/{id}` (등록자 본인 또는 MANAGER, 스펙 FR-10a).

    S-12 배정 화면에서 게스트 칩을 탭해 실력 등급을 즉시 고치는 용도. 보낸 필드만 바꾼다.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    skill_grade: int | None = Field(default=None, ge=1, le=5, description="1~5. 바꾸면 prior_overall이 다시 계산된다")
    height_cm: int | None = Field(default=None, ge=120, le=250, description="게스트 키(cm). 필드를 빼면 변경 없음, null 을 보내면 지운다")
    preferred_position: Position | None = Field(default=None, description="None이면 변경 없음")
    playable_positions: list[Position] | None = Field(default=None, description="None이면 변경 없음, 빈 배열이면 전부 해제")


class MergeRequest(BaseModel):
    """게스트 → 회원 병합 — `POST /players/{guest_player_id}:merge` (MANAGER 전용, S-08, FR-13).

    게스트가 팀 코드로 정식 가입하면 새 players 행이 생긴다. 매니저가 "이 사람이 지난주 게스트
    김OO" 이라고 지정하면 게스트 행의 `merged_into_player_id` 에 회원 행 id 를 적고 status 를 LEFT 로
    바꾼다. 행을 물리적으로 합치지 않으므로 `:unmerge` 로 되돌릴 수 있다 (6.2절, 13.2절 3항).
    URL 의 대상이 게스트가 아니면 422 MERGE_KIND_MISMATCH, 이미 병합됐으면 409 ALREADY_MERGED.
    """

    into_player_id: int = Field(description="기록을 넘겨받을 회원 players.id (같은 팀, kind=MEMBER)")


# --- 매니저 실력 정렬 (F14) ---


class RankingCreate(BaseModel):
    """매니저 실력 정렬 저장 — `POST /teams/{id}/rankings` (MANAGER 전용, S-19, FR-14).

    팀원 카드를 드래그해 만든 순서를 그대로 보낸다. 덮어쓰지 않고 **새 버전**으로 쌓이며
    이전 버전은 `is_active=false` 가 된다. 순서는 z-score 로 바뀌어 사전 실력값의 50% 를 차지한다
    (8.5절: `prior_final_z = 0.5 × 설문 + 0.5 × 정렬`). 다른 팀의 id 가 섞이면 422 PLAYER_NOT_IN_TEAM.
    """

    player_ids: list[int] = Field(min_length=2, max_length=MAX_RANKING_PLAYERS, description=f"상위 → 하위 순서 (최대 {MAX_RANKING_PLAYERS}명)")


class RankingEntryView(BaseModel):
    """정렬 한 줄. `RankingView.entries` 원소."""

    rank_no: int = Field(description="1이 가장 잘하는 사람")
    player: PlayerCard


class RankingView(BaseModel):
    """정렬 한 버전 — `GET /teams/{id}/rankings/latest`, `POST /teams/{id}/rankings`,
    `GET /teams/{id}/rankings` 의 items 원소 (MANAGER 전용).

    정렬이 한 번도 없으면 latest 는 404 NO_RANKING.
    """

    id: int = Field(description="manager_rankings.id")
    ranked_at: datetime = Field(description="이 버전을 저장한 시각")
    ranked_by: int = Field(description="정렬한 매니저의 users.id")
    is_active: bool = Field(description="현재 사전값 계산에 쓰이는 버전인지. 팀당 하나만 true")
    entries: list[RankingEntryView] = Field(description="rank_no 오름차순")


class GuestClaimView(BaseModel):
    """`GET /me/guest-claims` 의 items 원소 — "이전 모임에 게스트로 온 기록이 있어요. 본인이 맞나요?" 카드."""

    guest: PlayerCard
    team_id: int
    team_name: str
    member_player_id: int = Field(description="확인하면 기록이 합쳐질 내 players.id")
    events_attended: int
    quarters_played: int
    last_event_date: date | None = None


class GuestClaimIn(BaseModel):
    """`POST /players/{guest_player_id}:claim` 요청. accept=false 면 거절로 기록하고 다시 묻지 않는다."""

    accept: bool
