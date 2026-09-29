"""전술 추천 · 전술판 · 이름표 (docs/07 F20·F21, 8.3절).

- GET /tactics/presets                                   프리셋 전술 목록
- GET /events/{event_id}/tactics                         그날 이름표가 저장된 전술 목록 (참석자)
- GET /events/{event_id}/tactics/recommend               팀별 추천 전술 상위 3개 (매니저)
- GET /events/{event_id}/tactics/{play_key}              전술 + 그날 팀별 이름표 (참석자)
- PUT /events/{event_id}/tactics/{play_key}/slots        이름표 저장 (매니저)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, CurrentUser, EventManager, EventMember, get_event_or_404
from app.api.v1._docs import errors
from app.models import Event, Player
from app.schemas.tactic import EventPlayView, PresetList, SavedPlays, SlotsIn, TacticRecommendation
from app.services import tactic_service

router = APIRouter(tags=["전술"])
EventDep = Annotated[Event, Depends(get_event_or_404)]


def _me(db: DB, me: Player) -> Player:
    """ADMIN 가상 매니저(id 없음)는 그대로, 실제 참가자는 세션의 행으로."""
    return db.get(Player, me.id) if me.id else me


@router.get("/tactics/presets", response_model=PresetList, summary="프리셋 전술 목록")
def list_presets(user: CurrentUser):
    """앱에 들어 있는 전술 8개 (시작 위치 · 단계별 동작 · 슬롯 역할 · 대상 수비).

    - **권한:** 로그인 사용자.
    - **처리:** 정본은 `app/tactics/presets.py`. 전술을 고치면 `presets_version` 이 오른다.
    - **상태:** `구현됨`.
    """
    return tactic_service.presets()


@router.get(
    "/events/{event_id}/tactics", response_model=SavedPlays,
    responses=errors(_403=("NOT_A_MEMBER", "NOT_ATTENDEE")), summary="그날 이름표가 있는 전술",
)
def saved_plays(db: DB, me: EventMember, event: EventDep):
    """전술 탭에서 참석자에게 "오늘 이름표가 있는 전술" 을 보여 줄 때 쓴다.

    - **권한:** 그 일정 참석자(확정 배정에 들었거나 참석 응답) · 매니저 · ADMIN.
    - **오류:** `403 NOT_ATTENDEE`.
    - **상태:** `구현됨`.
    """
    return tactic_service.saved_plays(db, event, _me(db, me))


@router.get(
    "/events/{event_id}/tactics/recommend", response_model=TacticRecommendation,
    responses=errors(_403="FORBIDDEN_ROLE", _404="NOT_ADOPTED_YET"), summary="팀별 추천 전술",
)
def recommend(
    db: DB, me: EventManager, event: EventDep,
    squad_no: Annotated[int | None, Query(description="없으면 두 팀 모두")] = None,
    zone: Annotated[bool, Query(description="상대가 지역 수비를 쓰면 true")] = False,
):
    """확정 배정의 팀마다 적합도 상위 3개 전술과 슬롯 배치 (규칙 기반, LLM 없음).

    - **권한:** 매니저 · ADMIN. 충족/미충족 속성은 설문에서 나온 개인 특성이라 팀원에게 주지 않는다.
    - **처리:** 선수별 역할 점수(키는 참석자 안 백분위, 설문 없는 게스트는 참석자 평균) → 전술마다 5슬롯 최적 배치 →
      적합도 순. `zone=true` 면 zone·any 전술만, 아니면 man·any 전술만.
    - **오류:** `404 NOT_ADOPTED_YET`.
    - **상태:** `구현됨`.
    - **설계서:** docs/07 FR-43 ~ FR-45.
    """
    return tactic_service.recommend(db, event, squad_no=squad_no, zone=zone)


@router.get(
    "/events/{event_id}/tactics/{play_key}", response_model=EventPlayView,
    responses=errors(_403=("NOT_A_MEMBER", "NOT_ATTENDEE"), _404="NOT_FOUND"), summary="전술과 그날 이름표",
)
def play_view(db: DB, me: EventMember, event: EventDep, play_key: str):
    """전술판(S-29)이 쓰는 값. 확정 배정이 없으면 `squads` 가 비어 있다.

    - **권한:** 그 일정 참석자 · 매니저 · ADMIN.
    - **오류:** `403 NOT_ATTENDEE`, `404 NOT_FOUND` — 없는 전술.
    - **상태:** `구현됨`.
    """
    return tactic_service.play_view(db, event, play_key, _me(db, me))


@router.put(
    "/events/{event_id}/tactics/{play_key}/slots", response_model=EventPlayView,
    responses=errors(_400="VALIDATION_ERROR", _403="FORBIDDEN_ROLE", _404=("NOT_FOUND", "NOT_ADOPTED_YET"), _422="PLAYER_NOT_IN_SQUAD"),
    summary="전술 이름표 저장",
)
def save_slots(db: DB, user: CurrentUser, me: EventManager, event: EventDep, play_key: str, body: SlotsIn):
    """그날 한 팀의 이 전술 이름표를 통째로 바꾼다. 빈 목록이면 지운다.

    - **권한:** 매니저 · ADMIN.
    - **오류:** `400 VALIDATION_ERROR` — 같은 자리·같은 사람 중복. `422 PLAYER_NOT_IN_SQUAD` — 그날 그 팀이 아닌 선수.
      `404 NOT_ADOPTED_YET` — 확정 배정 없음.
    - **상태:** `구현됨`.
    """
    return tactic_service.save_slots(db, event, play_key, body, user, _me(db, me))
