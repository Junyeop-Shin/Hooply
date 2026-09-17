"""7.3절 일정 · 참석 — 일정 CRUD, RSVP, 참석 현황, **회차별 게스트 등록** (F4 · F13 · 게스트 기능 설계).

설계서: 7.3절 일정 · 참석, FR-08 · FR-09 · FR-15 · FR-34, 6.2절 `events` / `event_attendances`,
스펙 FR-10 · FR-10a · FR-11 · FR-11a.

엔드포인트
- POST   /teams/{team_id}/events                    일정 등록 (구현됨)
- GET    /teams/{team_id}/events                    일정 목록 (구현됨)
- GET    /events/{event_id}                         일정 상세 + 내 응답 (구현됨)
- PATCH  /events/{event_id}                         일정 수정 (구현됨)
- DELETE /events/{event_id}                         일정 취소 (구현됨)
- PUT    /events/{event_id}/attendance              내 참석 응답 (구현됨)
- PUT    /events/{event_id}/attendances/{player_id} 매니저 대리 응답 (구현됨)
- GET    /events/{event_id}/attendances             참석 현황 + 포지션 분포 (구현됨)
- POST   /events/{event_id}/guests                  회차에 게스트 등록 — 팀원 누구나 (구현됨)
- PATCH  /events/{event_id}/guests/{player_id}      회차 게스트 수정 — 등록자/매니저 (구현됨)
- DELETE /events/{event_id}/guests/{player_id}      회차 게스트 삭제(불참 처리) — 등록자/매니저 (구현됨)
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.deps import (
    DB,
    CurrentUser,
    EventManager,
    EventMember,
    TeamManager,
    TeamMember,
    get_event_or_404,
    get_team_or_404,
)
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Event, Player, Team
from app.models.enums import AttendanceStatus, EventStatus, TeamRole
from app.schemas.common import ItemList, Page, PageMeta
from app.schemas.event import (
    AttendanceList,
    AttendanceUpdate,
    AttendanceView,
    EventCreate,
    EventGuestCreate,
    EventGuestUpdate,
    EventUpdate,
    EventView,
    GuestPresetView,
)
from app.schemas.team import GuestSimilar
from app.services import event_service, guest_service
from app.services.player_service import to_card

router = APIRouter(tags=["일정 · 참석"])


@router.post(
    "/teams/{team_id}/events", status_code=201, response_model=EventView,
    responses=errors(_422="TEAM_NOT_ACTIVE"), summary="일정 등록",
)
def create_event(db: DB, me: TeamManager, user: CurrentUser, team: Annotated[Team, Depends(get_team_or_404)], body: EventCreate):
    """모임 일정(날짜·시간·장소·응답 마감)을 등록하고 팀원에게 RSVP를 연다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 팀이 `ACTIVE`(회원 5명 이상)인지 확인한다. `events(status=OPEN)`를 만들고 활성 회원
      전원에 `event_attendances(status=PENDING)` 행을 생성한다. 게스트 행은 만들지 않는다.
    - **오류:** `422 TEAM_NOT_ACTIVE`, `403 FORBIDDEN_ROLE`, `404 NOT_FOUND`, `400 VALIDATION_ERROR` — 종료<시작.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-06 · FR-08, F4, 5.4절 팀 미활성, S-09.
    """
    event = event_service.create_event(db, team, user, body)
    return event_service.event_view(db, event, me)


@router.get("/teams/{team_id}/events", response_model=Page[EventView], summary="일정 목록 조회")
def list_events(
    db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)],
    from_: Annotated[date | None, Query(alias="from", description="조회 시작일 (포함)")] = None,
    to: Annotated[date | None, Query(description="조회 종료일 (포함)")] = None,
    status: Annotated[EventStatus | None, Query(description="OPEN / CLOSED / DONE / CANCELED")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """팀의 일정을 기간·상태로 필터링해 최신순으로 돌려준다 (각 일정에 내 응답·참석 인원 포함).

    - **권한:** 팀원 또는 ADMIN.
    - **처리:** `events(team_id)`를 `event_date` 내림차순으로 페이징한다. 홈(S-04)과 팀 상세(S-07)가 쓴다.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, 7.1절 목록 응답 규약, S-04 · S-07.
    """
    items, total = event_service.list_events(db, team, me, date_from=from_, date_to=to, status=status, page=page, size=size)
    return Page(items=items, meta=PageMeta(page=page, size=size, total=total, has_next=page * size < total))


@router.get("/events/{event_id}", response_model=EventView, summary="일정 상세 조회")
def get_event(db: DB, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)]):
    """일정 정보와 내 참석 응답 상태, 지금 응답 가능한지(`rsvp_open`)를 돌려준다.

    - **권한:** 일정이 속한 팀의 팀원 또는 ADMIN.
    - **처리:** `events` 행 + 내 `event_attendances.status` + 참석 인원 수. S-10의 토글 초기값.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, S-10.
    """
    return event_service.event_view(db, event, me)


@router.patch("/events/{event_id}", response_model=EventView, summary="일정 수정")
def update_event(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)], body: EventUpdate):
    """일정의 날짜·시간·장소·응답 마감·메모를 부분 수정한다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 본문에 포함된 필드만 덮어쓴다. 마감을 미래로 늘리면 응답이 다시 열린다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`, `400 VALIDATION_ERROR`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-08.
    """
    return event_service.event_view(db, event_service.update_event(db, event, body), me)


@router.post("/events/{event_id}/rsvp:close", response_model=EventView, summary="응답 미리 마감")
def close_rsvp(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)]):
    """응답 마감 시각이 되기 전에 매니저가 참석 응답을 닫는다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** `status=CLOSED`. 이후 플레이어 본인 응답은 `422 RSVP_CLOSED`, 매니저 대리 응답·게스트 등록은 계속 가능하다.
      배정 확정(adopt)도 같은 상태로 만들므로 배정 화면에서 바로 누를 수 있게 둔다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`, `400 VALIDATION_ERROR` — OPEN 이 아닌 일정.
    - **상태:** `구현됨`.
    - **설계서:** FR-08 (참석 투표 마감), S-11 · S-12.
    """
    return event_service.event_view(db, event_service.close_rsvp(db, event), me)


@router.delete("/events/{event_id}", status_code=204, summary="일정 삭제")
def delete_event(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)]):
    """일정을 지운다. 상태만 바꾸지 않고 행을 삭제하며 이력을 남기지 않는다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 참석 응답·배정 실행과 후보안·경기 후 투표가 함께 지워진다. 이 일정에만 불렀던 게스트도
      다른 기록이 없으면 지운다(초대 이력은 남음). 경기 기록이 있는 `DONE` 일정은 지울 수 없다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`, `400 VALIDATION_ERROR` — 경기 기록이 있음.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-08, 6.2절 `events.status`.
    """
    event_service.delete_event(db, event)


@router.put(
    "/events/{event_id}/attendance", response_model=AttendanceView,
    responses=errors(_422="RSVP_CLOSED"), summary="내 참석 응답",
)
def respond_attendance(db: DB, me: EventMember, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], body: AttendanceUpdate):
    """일정에 참석/불참을 응답한다. 마감 전까지는 몇 번이든 바꿀 수 있다.

    - **권한:** 일정이 속한 팀의 팀원 (본인 응답만).
    - **처리:** 일정이 `OPEN`이고 `rsvp_deadline` 전이어야 한다. 내 행을 upsert 하고 `responded_at`을 기록.
    - **오류:** `422 RSVP_CLOSED`, `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-09, 5.4절 RSVP 마감 후 응답, S-10.
    """
    row = event_service.respond(db, event, me, body.status, body.note)
    player = db.get(Player, me.id)
    return event_service.attendance_view(db, row, player, user, me.role == TeamRole.MANAGER)


@router.put(
    "/events/{event_id}/attendances/{player_id}", response_model=AttendanceView,
    responses=errors(_403="FORBIDDEN_ROLE"), summary="매니저 대리 참석 등록",
)
def set_attendance_for(db: DB, me: EventManager, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], player_id: int, body: AttendanceUpdate):
    """매니저가 특정 참가자(회원·게스트)의 참석 상태를 대신 지정한다. RSVP 마감과 무관.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 대상이 이 팀의 활성 참가자인지 확인하고 upsert. `registered_by`에 매니저를 기록한다.
      노쇼·당일 인원 변동 처리에 쓴다. 게스트를 새로 부르는 경우는 `POST /events/{id}/guests`가 편하다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, 3.3절 "참석 응답 △ (매니저가 대신 등록)", S-11.
    """
    player = db.get(Player, player_id)
    if player is None:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    row = event_service.set_attendance(db, event, player, body.status, body.note, user)
    db.commit()
    return event_service.attendance_view(db, row, player, user, True)


@router.get("/events/{event_id}/attendances", response_model=AttendanceList, summary="참석 현황 · 포지션 분포")
def list_attendances(
    db: DB, me: EventMember, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)],
    status: Annotated[AttendanceStatus | None, Query(description="ATTEND / ABSENT / PENDING. 생략 시 전체")] = None,
):
    """참석/불참/미응답 명단(게스트 포함)과 포지션 분포 요약, 희소 자원 경고를 돌려준다.

    - **권한:** 일정이 속한 팀의 팀원 또는 ADMIN.
    - **처리:** 참석 행이 없는 회원은 PENDING으로 합성한다. 게스트 카드에는 등록자·묶기 요청·
      `can_edit`(호출자가 수정 가능한지)이 붙는다. `summary`에 포지션별 가능 인원, 1번/빅맨 수, 경고.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-15 · FR-34, 5.4절 빅맨 부족, S-11, 스펙 6절.
    """
    return event_service.attendance_list(db, event, me, user, status)


# --- 회차별 게스트 (게스트 기능 설계) ---


@router.post(
    "/events/{event_id}/guests", status_code=201, response_model=AttendanceView,
    responses={200: {"model": GuestSimilar, "description": "동명이인 후보 존재 — existing_player_id 또는 force_new 로 재요청"}},
    summary="회차에 게스트 등록",
)
def register_event_guest(db: DB, me: EventMember, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], body: EventGuestCreate):
    """게스트를 이 회차 참석자(ATTEND)로 추가한다. 게스트를 직접 부른 플레이어가 등록할 수 있다.

    - **권한:** 팀원 누구나 (ACTIVE) 또는 매니저/ADMIN — 스펙 FR-10.
    - **처리:** `existing_player_id`가 있으면 재방문 게스트 레코드를 재사용(기록 누적, FR-12). 없으면
      이름으로 새 게스트를 만들되 동명이인이 있고 `force_new=false`면 `200 {similar[]}`로 확인을 요청한다.
      `skill_grade`·`preferred_position`·`playable_positions`는 선택 (FR-11). `team_lock_request=true`면
      `team_lock_request_player_id = 등록자의 player_id`로 저장한다 (FR-11a) — 이는 요청일 뿐이며 매니저가
      배정 화면의 "묶기 제안"에서 승인해야 제약이 된다.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`, `400 VALIDATION_ERROR` — 취소된 일정.
    - **상태:** `구현됨`.
    - **설계서:** 스펙 2 · 4 · 5절, 설계서 FR-10 ~ FR-12, S-10 · S-11.
    """
    view, similar = event_service.register_guest(db, event, me, user, body)
    if similar is not None:
        return JSONResponse(status_code=200, content=GuestSimilar(similar=[to_card(p, include_grade=me.role == TeamRole.MANAGER) for p in similar]).model_dump(mode="json"))
    return view


@router.patch(
    "/events/{event_id}/guests/{player_id}", response_model=AttendanceView,
    responses=errors(_403="FORBIDDEN_NOT_OWNER"), summary="회차 게스트 수정",
)
def update_event_guest(db: DB, me: EventMember, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], player_id: int, body: EventGuestUpdate):
    """회차에 등록된 게스트의 이름·등급·포지션·묶기 요청·참석 상태를 수정한다.

    - **권한:** 등록자 본인 또는 팀 매니저 또는 ADMIN (스펙 FR-10a). 아니면 `403 FORBIDDEN_NOT_OWNER`.
    - **처리:** 보낸 필드만 반영한다. `team_lock_request`는 원래 등록자 기준으로 대상을 잡는다.
    - **오류:** `403 FORBIDDEN_NOT_OWNER`, `404 NOT_FOUND` — 이 회차에 없는 게스트.
    - **상태:** `구현됨`.
    - **설계서:** 스펙 3 · 5 · 7절.
    """
    guest = guest_service.require_guest(db, player_id)
    return event_service.update_event_guest(db, event, me, user, guest, body)


@router.delete(
    "/events/{event_id}/guests/{player_id}", status_code=204,
    responses=errors(_403="FORBIDDEN_NOT_OWNER"), summary="회차 게스트 삭제 (불참 처리)",
)
def remove_event_guest(db: DB, me: EventMember, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], player_id: int):
    """이 회차의 게스트 참석을 취소한다. `event_attendances` 행만 지우고 게스트 레코드는 남긴다.

    - **권한:** 등록자 본인 또는 팀 매니저 또는 ADMIN.
    - **처리:** 참석 행 삭제. `players` 원본은 다음 방문 때 재사용(FR-12). 이미 배정이 실행된 뒤라면
      배정 결과는 그대로 두고 프론트가 "재배정" 버튼을 보인다 (스펙 7절).
    - **오류:** `403 FORBIDDEN_NOT_OWNER`, `404 NOT_FOUND`.
    - **상태:** `구현됨`.
    - **설계서:** 스펙 5 · 7절, 5.4절 노쇼 / 당일 인원 변동.
    """
    guest = guest_service.require_guest(db, player_id)
    event_service.remove_event_guest(db, event, user, guest)


@router.get("/events/{event_id}/guests/presets", response_model=ItemList[GuestPresetView], summary="이전에 초대한 게스트 목록")
def guest_presets(db: DB, me: EventMember, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)]):
    """내가 이 팀에서 초대했던 게스트를 최근 사용순으로 돌려준다 — 게스트 초대 시트의 "불러오기".

    - **권한:** 팀원 (본인이 등록한 이력만).
    - **처리:** `guest_invite_presets(team_id, created_by=나)`. 항목을 고르면 이름·실력·선호/가능 포지션·같은 팀 요청이
      채워지고, `existing_player_id` 가 있으면 같은 게스트 레코드를 재사용해 기록이 이어진다.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** FR-12 재방문 게스트 누적 (사용자 요청으로 추가).
    """
    from app.models import Player as _P

    items = []
    for pr in event_service.my_presets(db, event.team_id, user):
        alive = pr.last_player_id and db.get(_P, pr.last_player_id)
        items.append(
            GuestPresetView(
                id=pr.id, display_name=pr.display_name, skill_grade=pr.skill_grade, height_cm=pr.height_cm, preferred_position=pr.preferred_position,
                playable_positions=pr.playable_positions, team_lock_request=pr.team_lock_request,
                existing_player_id=pr.last_player_id if (alive and alive.status == "ACTIVE" and alive.merged_into_player_id is None) else None,
                use_count=pr.use_count, last_used_at=pr.last_used_at,
            )
        )
    return ItemList(items=items)
