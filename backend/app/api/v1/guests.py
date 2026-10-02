"""7.3절 게스트 관리 — 게스트 레코드의 등록·검색·수정·회원 병합 (F13 · 게스트 기능 설계).

게스트는 액터가 아니라 데이터상의 참가자다 (3.1절). 기록·배정·투표의 **대상**은 되지만
로그인·설문·투표의 **주체**는 아니므로, `users` 없이 `players(kind=GUEST, user_id=NULL)`로만 존재한다.

회차(일정)에 게스트를 넣는 API 는 events 라우터의 `/events/{event_id}/guests` 다. 이 파일은 회차와 무관한
**게스트 레코드 자체** 를 다룬다.

권한 (스펙 3절): 등록은 팀원 누구나. 수정·삭제는 등록자 본인 또는 매니저. 병합은 매니저.

엔드포인트
- POST  /teams/{team_id}/guests                   게스트 레코드 등록 (구현됨)
- GET   /teams/{team_id}/guests                   기존 게스트 검색 (구현됨)
- GET   /teams/{team_id}/guests/merge-candidates  이름이 같은 게스트–회원 쌍 (구현됨, MANAGER)
- PATCH /players/{player_id}                      게스트 이름·등급·포지션 수정 (구현됨)
- POST  /players/{guest_player_id}:merge          게스트 → 회원 병합 (구현됨, MANAGER)
- POST  /players/{player_id}:unmerge              병합 되돌리기 (구현됨, MANAGER)
- GET   /me/guest-claims                          같은 이름의 게스트 기록 중 내가 아직 확인 안 한 것 (구현됨)
- POST  /players/{guest_player_id}:claim          본인 확인 → 병합 / 거절 (구현됨)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.deps import DB, CurrentUser, TeamManager, TeamMember, get_team_or_404
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Team
from app.models.enums import TeamRole
from app.schemas.common import ItemList, PlayerCard
from app.schemas.team import (
    GuestClaimIn,
    GuestClaimView,
    GuestCreate,
    GuestSimilar,
    MergeCandidate,
    MergeRequest,
    PlayerUpdate,
)
from app.services import guest_service
from app.services.player_service import to_card as _to_card


def to_card(p, *, include_grade=False):
    """기본은 등급을 빼고 돌려준다 (9.2절 표시 정책). 등급을 볼 수 있는 쪽에서만 `include_grade=True` 를 준다."""
    return _to_card(p, include_grade=include_grade)

router = APIRouter(tags=["게스트 관리"])


@router.post(
    "/teams/{team_id}/guests", status_code=201, response_model=PlayerCard,
    responses={200: {"model": GuestSimilar, "description": "동명이인 후보 존재 — 확인 요청"}},
    summary="게스트 레코드 등록",
)
def create_guest(db: DB, me: TeamMember, user: CurrentUser, team: Annotated[Team, Depends(get_team_or_404)], body: GuestCreate):
    """계정 없는 게스트를 이름만으로 팀 참가자에 추가한다 (회차와 무관한 레코드).

    - **권한:** 팀원 누구나 (스펙 FR-10 확장) 또는 ADMIN. 등록자가 `created_by`로 기록된다.
    - **처리:** 같은 팀에 같은 이름의 게스트가 있고 `force_new=false`이면 201 대신 `200 {similar[]}`로
      기존 후보를 돌려준다. 신규면 `players(kind=GUEST)`를 만든다. `skill_grade`를 주면 클럽 회원
      prior 분포의 분위수로 `prior_overall`, `prior_source=MANAGER`, `confidence=0.25`; 없으면 클럽 평균·
      `DEFAULT`·`confidence=0`.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`, `400 VALIDATION_ERROR`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-10 · FR-11, 5.4절 동명이인, 9.5절 게스트 배정, 스펙 2~4절.
    """
    similar = guest_service.find_similar(db, team.id, body.display_name)
    if similar and not body.force_new:
        return JSONResponse(status_code=200, content=GuestSimilar(similar=[to_card(p) for p in similar]).model_dump(mode="json"))
    guest = guest_service.create_guest(
        db, team, user, display_name=body.display_name, skill_grade=body.skill_grade,
        preferred_position=body.preferred_position, playable_positions=body.playable_positions, height_cm=body.height_cm,
    )
    db.commit()
    db.refresh(guest)
    return to_card(guest, include_grade=True)  # 방금 본인이 입력한 값


@router.get("/teams/{team_id}/guests", response_model=ItemList[PlayerCard], summary="기존 게스트 검색")
def search_guests(
    db: DB, me: TeamMember, team: Annotated[Team, Depends(get_team_or_404)],
    q: Annotated[str | None, Query(description="이름 부분 일치 검색어. 생략 시 팀의 게스트 전체")] = None,
):
    """재방문 게스트를 골라 기록을 이어 붙이기 위해 기존 게스트 레코드를 검색한다.

    - **권한:** 팀원 또는 ADMIN. 실력 등급은 매니저에게만 실린다.
    - **처리:** `players(team_id, kind=GUEST, status=ACTIVE)` 를 이름 부분 일치로 찾는다.
      회차 게스트 등록 시 `existing_player_id` 로 넘길 후보 목록이다.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-12, S-11.
    """
    show_grade = me.role == TeamRole.MANAGER  # 매니저가 매긴 등급은 매니저에게만 (9.2절)
    return ItemList(items=[to_card(p, include_grade=show_grade) for p in guest_service.search_guests(db, team.id, q)])


@router.get(
    "/teams/{team_id}/guests/merge-candidates", response_model=ItemList[MergeCandidate],
    responses=errors(_403="FORBIDDEN_ROLE"), summary="게스트–회원 병합 후보",
)
def merge_candidates(db: DB, me: TeamManager, team: Annotated[Team, Depends(get_team_or_404)]):
    """이름이 같은 게스트와 회원의 쌍을 찾아 준다 — "게스트로 오던 사람이 가입했을 때" 기록 승계 힌트.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 미병합 게스트의 `display_name`과 회원의 표시 이름·이름·닉네임을 대소문자 무시로
      비교한다. 동명이인일 수 있으므로 **자동 병합하지 않고** 매니저가 확인 후 `:merge`를 부른다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** FR-13, 6.2절 병합 절차, S-08 계정 연결.
    """
    pairs = guest_service.merge_candidates(db, team.id)
    return ItemList(items=[MergeCandidate(guest=to_card(g, include_grade=True), member=to_card(m, include_grade=True)) for g, m in pairs])


@router.patch(
    "/players/{player_id}", response_model=PlayerCard,
    responses=errors(_403="FORBIDDEN_NOT_OWNER"), summary="게스트 정보 수정",
)
def update_player(db: DB, user: CurrentUser, player_id: int, body: PlayerUpdate):
    """게스트의 표시 이름·실력 등급·선호/가능 포지션을 수정한다.

    - **권한:** 등록자 본인 또는 팀 매니저 또는 ADMIN (스펙 FR-10a).
    - **처리:** 보낸 필드만 바꾼다 (`height_cm: null` 을 명시하면 키를 지우고, 필드를 빼면 그대로 둔다). `skill_grade`를 보내면 `prior_overall`을 재환산하고
      `skill_rating_history(source=MANAGER_ADJUST)`를 남긴다. S-12에서 게스트 칩을 탭해 등급을 즉시
      고치는 흐름이 이 API를 쓴다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_NOT_OWNER`, `400 VALIDATION_ERROR` — 게스트가 아님.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH /players/{player_id}`), F13, 스펙 3절 · 5절.
    """
    guest = guest_service.require_guest(db, player_id)
    if not guest_service.can_manage_guest(db, user, guest):
        raise E.ForbiddenNotOwner()
    fields = body.model_dump(exclude_unset=True)
    guest_service.update_guest(
        db, guest, user, display_name=body.display_name, skill_grade=body.skill_grade,
        preferred_position=body.preferred_position, playable_positions=body.playable_positions,
        grade_given="skill_grade" in fields, height_cm=body.height_cm, height_given="height_cm" in fields,
    )
    db.commit()
    db.refresh(guest)
    return to_card(guest, include_grade=True)


@router.post(
    "/players/{guest_player_id}:merge", response_model=PlayerCard,
    responses=errors(_403="FORBIDDEN_ROLE", _409="ALREADY_MERGED", _422="MERGE_KIND_MISMATCH"),
    summary="게스트를 회원 계정에 병합",
)
def merge_guest(db: DB, user: CurrentUser, guest_player_id: int, body: MergeRequest):
    """정식 가입한 회원에게 과거 게스트 기록을 승계시킨다. 물리 병합은 하지 않는다.

    - **권한:** 해당 팀의 매니저 또는 ADMIN.
    - **처리:** 게스트 행의 `merged_into_player_id`에 회원 행을 기록하고 `status=LEFT`. 지표 계산은
      이 포인터를 따라 합산하므로 쿼터·배정·투표 데이터가 보존되고 `:unmerge`로 되돌릴 수 있다.
      `skill_rating_history(source=MERGE)`를 남긴다.
    - **오류:** `409 ALREADY_MERGED`, `422 MERGE_KIND_MISMATCH` — 대상이 같은 팀 회원이 아님,
      `403 FORBIDDEN_ROLE`, `404 NOT_FOUND`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-13, 6.2절 병합 절차, 13.2절 3항, S-08.
    """
    guest = guest_service.require_guest(db, guest_player_id)
    if not guest_service.is_manager(db, user, guest.team_id):
        raise E.ForbiddenRole()
    target = guest_service.merge(db, guest, body.into_player_id)
    db.refresh(target)
    return to_card(target, include_grade=True)  # 매니저만 호출한다


@router.post(
    "/players/{player_id}:unmerge", response_model=PlayerCard,
    responses=errors(_403="FORBIDDEN_ROLE", _404="NOT_FOUND"), summary="게스트 병합 되돌리기",
)
def unmerge_guest(db: DB, user: CurrentUser, player_id: int):
    """잘못된 병합을 취소해 게스트 레코드를 독립 상태로 되돌린다.

    - **권한:** 해당 팀의 매니저 또는 ADMIN.
    - **처리:** `merged_into_player_id`를 NULL, `status`를 ACTIVE로 되돌린다. 포인터 방식이라 한 번의 갱신.
    - **오류:** `404 NOT_FOUND` — 병합 상태가 아님. `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, 6.2절 병합 절차, 13.2절 3항.
    """
    guest = guest_service.require_guest(db, player_id)
    if not guest_service.is_manager(db, user, guest.team_id):
        raise E.ForbiddenRole()
    guest_service.unmerge(db, guest)
    db.refresh(guest)
    return to_card(guest, include_grade=True)  # 매니저만 호출한다


@router.get("/me/guest-claims", response_model=ItemList[GuestClaimView], summary="내 것일 수 있는 게스트 기록")
def my_guest_claims(db: DB, user: CurrentUser):
    """내가 속한 팀에서 내 이름(이름·닉네임, "게스트 " 접두어 무시)과 같은 미병합 게스트 중 아직 확인·거절하지 않은 것.

    - **권한:** 로그인 사용자.
    - **처리:** 참석 회차 수·출전 쿼터 수·마지막 참석일을 함께 준다. 홈 화면이 이 목록으로 "본인이 맞나요?" 카드를 띄운다.
    - **상태:** `구현됨`.
    """
    items = []
    for g, me, summary in guest_service.pending_claims(db, user):
        team = db.get(Team, g.team_id)
        items.append(GuestClaimView(guest=to_card(g), team_id=g.team_id, team_name=team.name if team else "", member_player_id=me.id, **summary))
    return ItemList(items=items)


@router.post(
    "/players/{guest_player_id}:claim", response_model=ItemList[GuestClaimView],
    responses=errors(_403=("FORBIDDEN_ROLE", "NOT_A_MEMBER"), _409="ALREADY_MERGED"), summary="게스트 기록 본인 확인 (병합 / 거절)",
)
def claim_guest(db: DB, user: CurrentUser, guest_player_id: int, body: GuestClaimIn):
    """게스트 기록이 내 것이면 내 계정(그 팀의 players 행)으로 병합하고, 아니면 거절로 기록해 다시 묻지 않는다.

    - **권한:** 그 팀에 속한 회원 본인. 이름이 같은 게스트만 가능 (다르면 매니저 병합 경로).
    - **처리:** 확인 시 `merged_into_player_id` 로 병합(매니저 병합과 동일)하고 팀 실력 지표를 재계산한다. 되돌리기는 매니저의 `:unmerge`.
    - **오류:** `403 NOT_A_MEMBER / FORBIDDEN_ROLE`, `409 ALREADY_MERGED`, `404 NOT_FOUND`.
    - **상태:** `구현됨`. 응답은 남은 확인 목록.
    """
    guest = guest_service.require_guest(db, guest_player_id)
    guest_service.claim(db, user, guest, body.accept)
    return my_guest_claims(db, user)
