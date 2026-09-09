"""7.3절 경기 기록 (F8 · F10) — 쿼터 기록 CRUD와 잔차 기반 실력 갱신.

기록은 매니저가 활동이 끝난 뒤 한 번에 입력한다 (2.5절). 저장 시 서버가 출전 10명의 코트 마진을 계산하고,
팀의 모든 쿼터를 시간순으로 재생해 실력 지표를 갱신한다 (9.2절 층 1 Elo). 삭제·수정도 같은 재계산을 거치므로
마진 롤백이 자동으로 성립한다 (13.2절 2항). 첫 2회 모임의 기록은 지표에 넣지 않는다 (13.2절 1항).

설계서: 7.3절 경기 기록, FR-25 ~ FR-27, 6.2절 quarters / quarter_lineups, 9.1 ~ 9.2절, S-15.
로테이션 자동 제안(F17, GET /events/{id}/rotation-suggestion)은 서비스 범위에서 제외했다.

엔드포인트
- POST   /events/{event_id}/quarters   쿼터 1건 추가 (구현됨)
- PUT    /events/{event_id}/quarters   여러 쿼터 일괄 저장 — 경기 후 한 번에 (구현됨)
- GET    /events/{event_id}/quarters   쿼터 + 라인업 + 요약 (구현됨)
- PATCH  /quarters/{quarter_id}        스코어·라인업 수정 (구현됨)
- DELETE /quarters/{quarter_id}        쿼터 삭제 → 마진 롤백 (구현됨)
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DB, CurrentUser, EventManager, EventMember, get_event_or_404
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Event
from app.schemas.game import (
    QuarterBulkResult,
    QuarterBulkSave,
    QuarterIn,
    QuarterListView,
    QuarterUpdate,
    QuarterView,
)
from app.services import guest_service, quarter_service

router = APIRouter(tags=["경기 기록"])


@router.post(
    "/events/{event_id}/quarters", status_code=201, response_model=QuarterView,
    responses=errors(_400="INVALID_LINEUP_SIZE", _409="QUARTER_EXISTS", _422="PLAYER_NOT_IN_TEAM"), summary="쿼터 1건 추가",
)
def add_quarter(db: DB, me: EventManager, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], body: QuarterIn):
    """쿼터 하나를 기록한다. 출전 10명(팀당 5명)과 스코어, 쿼터 길이.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 라인업을 검증(사이드별 5명, 중복 없음, 팀 참가자)하고 `raw_margin = 내 팀 − 상대 팀`,
      `normalized_margin = raw × 10 / duration_min` 을 10명 전원에 저장한다. 이어서 팀 전체 실력을 재계산하고
      일정을 `DONE` 으로 바꾼다.
    - **오류:** `400 INVALID_LINEUP_SIZE` — "블랙 팀 4명이 선택되었어요". `409 QUARTER_EXISTS`. `422 PLAYER_NOT_IN_TEAM`.
    - **상태:** `구현됨`.
    - **설계서:** FR-25 · FR-27, 6.2절 코트 마진 계산, 9.2절.
    """
    return quarter_service.quarter_view(db, quarter_service.add_quarter(db, event, user, body))


@router.put(
    "/events/{event_id}/quarters", response_model=QuarterBulkResult,
    responses=errors(_400="INVALID_LINEUP_SIZE", _422="PLAYER_NOT_IN_TEAM"), summary="쿼터 일괄 저장",
)
def bulk_save_quarters(db: DB, me: EventManager, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], body: QuarterBulkSave):
    """그 회차의 쿼터 전체를 한 번에 저장한다 — 경기 후 입력하는 실제 흐름(S-15 "일괄 저장").

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** `quarter_no` 기준으로 있으면 수정, 없으면 생성, 목록에서 빠졌으면 삭제(마진 롤백). 한 번의
      트랜잭션으로 처리한 뒤 팀 실력을 재계산한다. 응답은 `{created, updated, deleted}`.
    - **오류:** `400 INVALID_LINEUP_SIZE / VALIDATION_ERROR`(quarter_no 중복), `422 PLAYER_NOT_IN_TEAM`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PUT /events/{id}/quarters`), 2.4절 "기록 입력은 경기 후", 5.4절 쿼터 수 변경.
    """
    return quarter_service.bulk_save(db, event, user, body)


@router.get("/events/{event_id}/quarters", response_model=QuarterListView, summary="쿼터 기록 조회")
def list_quarters(db: DB, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)]):
    """쿼터별 스코어·라인업·마진과 요약(총점, 쿼터 승수, 참가자별 출전 수)을 돌려준다.

    - **권한:** 일정이 속한 팀의 팀원 또는 ADMIN. 스코어는 실력 수치가 아니므로 마스킹하지 않는다.
    - **처리:** `quarters(event_id)` + `quarter_lineups` 를 quarter_no 순으로.
    - **오류:** `404 NOT_FOUND`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, S-15.
    """
    return quarter_service.list_quarters(db, event)


def _manager_quarter(db, user, quarter_id: int):
    q = quarter_service.get_quarter(db, quarter_id)
    event = db.get(Event, q.event_id)
    if not guest_service.is_manager(db, user, event.team_id):
        raise E.ForbiddenRole()
    return q


@router.patch(
    "/quarters/{quarter_id}", response_model=QuarterView,
    responses=errors(_400="INVALID_LINEUP_SIZE", _403="FORBIDDEN_ROLE"), summary="쿼터 수정",
)
def update_quarter(db: DB, user: CurrentUser, quarter_id: int, body: QuarterUpdate):
    """스코어·길이·라인업을 고치고 마진과 실력 지표를 다시 계산한다.

    - **권한:** 그 팀의 매니저 또는 ADMIN.
    - **처리:** 보낸 필드만 바꾼다. `lineups` 는 보내면 10명 전체로 교체. 이후 팀 전체 재계산.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`, `400 INVALID_LINEUP_SIZE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH /quarters/{id}`), 13.2절 2항.
    """
    q = _manager_quarter(db, user, quarter_id)
    return quarter_service.quarter_view(db, quarter_service.update_quarter(db, q, body))


@router.delete("/quarters/{quarter_id}", status_code=204, responses=errors(_403="FORBIDDEN_ROLE"), summary="쿼터 삭제 (마진 롤백)")
def delete_quarter(db: DB, user: CurrentUser, quarter_id: int):
    """쿼터를 지우고 그 쿼터가 지표에 준 영향을 되돌린다.

    - **권한:** 그 팀의 매니저 또는 ADMIN.
    - **처리:** 행 삭제 후 팀의 남은 쿼터를 처음부터 재생해 실력 지표를 다시 쓴다. 남은 쿼터가 없으면 일정을
      `CLOSED` 로 되돌린다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`DELETE /quarters/{id}`), 5.4절 쿼터 수 변경, 13.2절 2항 "쿼터 삭제 시 마진을 롤백한다".
    """
    q = _manager_quarter(db, user, quarter_id)
    quarter_service.delete_quarter(db, q)
