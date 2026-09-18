"""7.3절 팀 배정 — 배정 실행, 제약 검증, 후보안 조회·수정·확정 (F5, F6, F7, F15, F16).

9.5~9.7절 알고리즘의 API 표면이다. 12~14명 2팀 규모에서는 완전 탐색으로 전역 최적을 보장하고,
LOCK/SEPARATE/PIN 제약은 Union-Find 슈퍼노드로 축약해 어떤 전략에서도 위반이 불가능하게 한다.
제약은 회차별(`assignment_runs` 종속)이며 다음 회차에 자동 승계되지 않는다.

설계서: 7.3절 팀 배정, FR-16 ~ FR-24 · FR-33 · FR-34, 9.5절 알고리즘, 9.6절 제약, 9.7절 계산량,
6.2절 배정 5개 테이블.

엔드포인트
- POST  /events/{event_id}/assignments                  배정 실행 → 후보안 3개 (구현됨)
- POST  /events/{event_id}/assignments:validate         제약 실현가능성 검사 (구현됨)
- GET   /events/{event_id}/assignments                  배정 실행 이력 (구현됨)
- GET   /events/{event_id}/assignments/last-constraints 직전 회차 제약 불러오기 (구현됨)
- GET   /assignments/runs/{run_id}                      후보안 3개 + 지표 + 설명 (구현됨)
- PATCH /assignments/candidates/{candidate_id}          선수 교체 후 재계산 (구현됨)
- POST  /assignments/candidates/{candidate_id}:adopt    후보안 확정 (구현됨)
- GET   /events/{event_id}/assignment/adopted           확정 결과 (액터별 마스킹) (구현됨)
- GET   /events/{event_id}/assignment/suggestions       게스트 묶기 제안 목록 (구현됨, 게스트 기능 설계)
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DB, CurrentUser, EventManager, EventMember, get_event_or_404
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Event, Player
from app.schemas.assignment import (
    AdoptedAssignment,
    AssignmentRunRequest,
    AssignmentRunView,
    CandidateView,
    ConstraintSet,
    SwapRequest,
    ValidateResult,
)
from app.schemas.common import ItemList
from app.schemas.event import LockSuggestion
from app.services import assignment_service, event_service, guest_service

router = APIRouter(tags=["팀 배정"])


@router.get(
    "/events/{event_id}/assignment/suggestions", response_model=ItemList[LockSuggestion],
    responses=errors(_403="FORBIDDEN_ROLE"), summary="게스트 묶기 제안 목록",
)
def lock_suggestions(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)]):
    """이 회차 참석 게스트 중 "OO와 같은 팀으로" 요청이 있는 것을 묶기 제안으로 돌려준다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** `event_attendances.team_lock_request_player_id`가 있고 게스트·대상 모두 ATTEND인 행만.
      대상이 불참으로 바뀌면 자동으로 빠진다 (스펙 7절). S-12 대기 칸의 "묶기 제안" 배지가 이 데이터이며,
      매니저가 승인하면 배정 실행 본문의 `lock_groups`에 `[guest_id, target_id]`를 넣는다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 스펙 4 · 5 · 6절, 설계서 9.6절 LOCK.
    """
    return ItemList(items=event_service.lock_suggestions(db, event))

_CONSTRAINT_ERRORS = (
    "LOCK_GROUP_TOO_LARGE", "CONSTRAINT_CONFLICT", "SEPARATE_INFEASIBLE",
    "LOCK_PARTITION_INFEASIBLE", "SQUAD_OVERFLOW", "NOT_ENOUGH_PLAYERS",
)


@router.post(
    "/events/{event_id}/assignments", status_code=201, response_model=AssignmentRunView,
    responses=errors(_422=_CONSTRAINT_ERRORS), summary="팀 배정 실행",
)
def run_assignment(db: DB, me: EventManager, user: CurrentUser, event: Annotated[Event, Depends(get_event_or_404)], body: AssignmentRunRequest):
    """참석 확정자를 팀으로 나눠 전략별 후보안(실력 우선 / 친화도 우선 / 종합)을 만든다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** ① 제약 실현가능성 검사 → ② PIN 고정, LOCK 은 Union-Find 슈퍼노드로 축약 → ③ 2팀 완전 탐색
      (모든 분할을 목적함수로 평가) → ④ 각 팀에 1번·5번 가능자가 있는 해만 남김(없으면 완화+경고) →
      ⑤ 전략별 최솟값을 후보안으로 저장(후보안끼리 편성이 겹치지 않게) → ⑥ 포지션 슬롯 배정과 설명 생성.
      `lock_groups` 에는 묶기 제안(`assignment/suggestions`)에서 승인한 `[게스트, 등록자]` 쌍을 넣는다.
      같은 회차에서 다시 실행하면 새 run 이 쌓이고 이전 결과는 이력으로 남는다.
    - **오류:** `422 NOT_ENOUGH_PLAYERS / LOCK_GROUP_TOO_LARGE / CONSTRAINT_CONFLICT / SEPARATE_INFEASIBLE /
      LOCK_PARTITION_INFEASIBLE / SQUAD_OVERFLOW / PLAYER_NOT_IN_TEAM` — `details[]`에 문제 그룹·선수.
      `400 VALIDATION_ERROR` — 3팀 이상, 취소된 일정.
    - **상태:** `구현됨`.
    - **설계서:** 9.5절 알고리즘, 9.6절 제약, 9.7절 완전 탐색, FR-16 ~ FR-21, FR-33, S-12.
    """
    run_row, warnings = assignment_service.run(db, event, user, body)
    return assignment_service.run_view(db, run_row, warnings)


@router.post("/events/{event_id}/assignments:validate", response_model=ValidateResult, summary="배정 제약 실현가능성 검사")
def validate_constraints(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)], body: AssignmentRunRequest):
    """실행 전 프리플라이트. 차단 사유(`violations[]`)와 경고(`warnings[]`)를 돌려주며 아무것도 저장하지 않는다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 인원 수, 묶음 크기 > 정원, 묶기·갈라놓기 충돌, 사전 배치 정원 초과, 분할 가능성을 검사한다.
      S-12 화면은 제약을 바꿀 때마다 이 API 로 실행 버튼 활성 여부를 정한다 (FR-20).
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 9.6절 사전 실현가능성 검사 표, FR-20, 13.2절 5항.
    """
    return assignment_service.validate(db, event, body)


@router.get("/events/{event_id}/assignments", response_model=ItemList[AssignmentRunView], summary="배정 실행 이력")
def list_runs(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)]):
    """이 회차의 배정 실행을 최신순으로 돌려준다 (재배정 이력 보존).

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** `assignment_runs(event_id)` 와 각 run 의 후보안·제약.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 6.3절 "events → assignment_runs 1:N (재배정 시 이력 누적)".
    """
    return ItemList(items=assignment_service.list_runs(db, event))


@router.get(
    "/events/{event_id}/assignments/last-constraints", response_model=ConstraintSet,
    responses=errors(_404="NOT_FOUND"), summary="직전 회차 제약 불러오기",
)
def last_constraints(db: DB, me: EventManager, event: Annotated[Event, Depends(get_event_or_404)]):
    """같은 팀의 직전 회차에서 마지막으로 실행한 배정의 제약을 돌려준다.

    - **권한:** 팀 매니저 또는 ADMIN.
    - **처리:** 제약은 회차별이라 자동 승계되지 않는다 (FR-18). 편의로 불러오기만 제공하며, 이번 회차 참석자가
      아닌 사람이 섞여 있으면 실행 시 `PLAYER_NOT_IN_TEAM` 으로 걸러진다.
    - **오류:** `404 NOT_FOUND` — 직전 기록 없음.
    - **상태:** `구현됨`.
    - **설계서:** 9.6절 저장 위치, FR-18.
    """
    return assignment_service.last_constraints(db, event)


@router.get("/assignments/runs/{run_id}", response_model=AssignmentRunView, summary="배정 실행 결과 조회")
def get_run(db: DB, user: CurrentUser, run_id: int):
    """후보안 3개 + 지표 + 설명을 돌려준다 (S-13).

    - **권한:** 그 팀의 매니저 또는 ADMIN.
    - **처리:** run 의 후보안 전부를 팀별 카드(수치 포함)와 함께 돌려준다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절, FR-21, S-13.
    """
    run_row = assignment_service.get_run(db, run_id)
    event = db.get(Event, run_row.event_id)
    if not guest_service.is_manager(db, user, event.team_id):
        raise E.ForbiddenRole()
    return assignment_service.run_view(db, run_row)


@router.patch(
    "/assignments/candidates/{candidate_id}", response_model=CandidateView,
    responses=errors(_409="ALREADY_ADOPTED", _422="INVALID_SWAP"), summary="후보안 선수 교체",
)
def swap_players(db: DB, user: CurrentUser, candidate_id: int, body: SwapRequest):
    """두 선수를 맞바꾸거나(`swaps`), 한 명을 옮기거나(`moves`), 그룹끼리 교환하고(`exchanges`) 지표·설명을 즉시 재계산한다 (F7).

    묶음(LOCK)에 속한 사람은 자동으로 묶음 전체가 함께 움직인다. 갈라놓기(SEPARATE)는 교환 뒤에도 다른 팀이어야 한다.

    - **권한:** 그 팀의 매니저 또는 ADMIN.
    - **처리:** 교체된 슬롯은 `is_manual_override=true`. 묶음(LOCK)·사전 배치(PIN)에 속한 사람은 개별로
      옮길 수 없다. 확정된 후보안은 수정할 수 없다 (재배정 실행).
    - **오류:** `422 INVALID_SWAP`, `409 ALREADY_ADOPTED`, `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** FR-22, F7, S-13 드래그 swap.
    """
    cand = assignment_service._load_candidate(db, candidate_id)
    event = db.get(Event, cand.run.event_id)
    if not guest_service.is_manager(db, user, event.team_id):
        raise E.ForbiddenRole()
    if body.swaps:
        cand = assignment_service.swap(db, cand, body.swaps)
    if body.moves:
        cand = assignment_service.move(db, cand, body.moves)
    if body.exchanges:
        cand = assignment_service.exchange(db, cand, body.exchanges)
    return assignment_service.candidate_view(db, cand)


@router.post(
    "/assignments/candidates/{candidate_id}:reset", response_model=CandidateView,
    responses=errors(_409="ALREADY_ADOPTED"), summary="수동 수정 초기화",
)
def reset_candidate(db: DB, user: CurrentUser, candidate_id: int):
    """매니저가 손으로 옮긴 것을 모두 되돌려 알고리즘이 낸 원래 편성으로 복원한다.

    - **권한:** 그 팀의 매니저 또는 ADMIN.
    - **처리:** 후보안에 저장된 원본 편성(`metrics.original_squads`)으로 슬롯을 되돌리고 지표를 재계산한다.
    - **오류:** `409 ALREADY_ADOPTED`, `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** F7 (사용자 요청으로 추가).
    """
    cand = assignment_service._load_candidate(db, candidate_id)
    event = db.get(Event, cand.run.event_id)
    if not guest_service.is_manager(db, user, event.team_id):
        raise E.ForbiddenRole()
    return assignment_service.candidate_view(db, assignment_service.reset_manual(db, cand))


@router.post(
    "/assignments/candidates/{candidate_id}:adopt", response_model=CandidateView,
    responses=errors(_409="ALREADY_ADOPTED"), summary="후보안 확정",
)
def adopt_candidate(db: DB, user: CurrentUser, candidate_id: int):
    """후보안을 확정해 참석자에게 공개한다 (FR-23). 일정은 CLOSED(응답 마감·배정 단계)가 된다.

    - **권한:** 그 팀의 매니저 또는 ADMIN.
    - **처리:** 같은 회차의 다른 확정을 해제하고 이 후보안을 `is_adopted=true` 로. 노쇼 등으로 재배정하면
      새 run 을 실행해 다시 확정한다.
    - **오류:** `409 ALREADY_ADOPTED` — 같은 run 안에 이미 확정된 다른 후보안. `404`, `403`.
    - **상태:** `구현됨`.
    - **설계서:** FR-23, 6.2절 부분 유니크 인덱스.
    """
    cand = assignment_service._load_candidate(db, candidate_id)
    event = db.get(Event, cand.run.event_id)
    if not guest_service.is_manager(db, user, event.team_id):
        raise E.ForbiddenRole()
    return assignment_service.candidate_view(db, assignment_service.adopt(db, cand))


@router.get(
    "/events/{event_id}/assignment/adopted", response_model=AdoptedAssignment,
    responses=errors(_404="NOT_ADOPTED_YET"), summary="확정된 배정 결과",
)
def adopted_assignment(db: DB, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)]):
    """확정된 편성을 돌려준다. 플레이어에게는 수치를 숨기고 문장 설명만 준다 (S-14).

    - **권한:** 일정이 속한 팀의 팀원 또는 ADMIN.
    - **처리:** MANAGER 는 `avg_skill`·수치 설명, PLAYER 는 `avg_skill=None`·포지션 중심 문장. `my_squad_no`,
      `my_assigned_position` 은 호출자 기준.
    - **오류:** `404 NOT_ADOPTED_YET`, `403 NOT_A_MEMBER`.
    - **상태:** `구현됨`.
    - **설계서:** FR-24, S-14, 9.2절 표시 정책.
    """
    player = db.get(Player, me.id) if me.id else me
    return assignment_service.adopted_view(db, event, player)
