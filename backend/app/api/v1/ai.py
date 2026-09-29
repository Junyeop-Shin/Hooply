"""AI 배정 설명 (docs/07 F19, 8.3절). 버튼을 눌렀을 때만 부른다 — 확정할 때 자동으로 부르지 않는다 (FR-50).

- POST /assignments/candidates/{candidate_id}/ai-explanation   체인 A · 매니저용
- GET  /events/{event_id}/assignment/adopted/ai-message        체인 B · 팀원용 (내 것만)
- POST /events/{event_id}/tactics/ai-recommend                 체인 C · 전술 추천 설명 (참석자)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, CurrentUser, EventMember, get_event_or_404
from app.api.v1._docs import errors
from app.core import errors as E
from app.models import Event, Player
from app.schemas.ai import AiExplanation, AiMessage, AiTactics
from app.services import ai_service, assignment_service, guest_service

router = APIRouter(tags=["AI 설명"])


@router.post(
    "/assignments/candidates/{candidate_id}/ai-explanation", response_model=AiExplanation,
    responses=errors(_403="FORBIDDEN_ROLE", _404="NOT_FOUND", _429="RATE_LIMITED"), summary="AI 배정 설명 (매니저용)",
)
def ai_explanation(db: DB, user: CurrentUser, candidate_id: int):
    """배정안 하나를 요약 · 수치 근거 2~3개 · 경기 중 확인할 점으로 설명한다 (LangChain · 체인 A).

    - **권한:** 그 일정 팀의 매니저 · ADMIN.
    - **처리:** 선수·팀은 가명(P1…, A·B)으로 보내고 결과를 실명으로 되돌린다. 입력에 없는 사람·숫자는 걸러낸다.
      같은 배정이면 저장해 둔 결과를 다시 쓴다(LLM 호출 없음). 키가 없거나 실패하면 `fallback=true` 와 기존 설명 `text`.
    - **오류:** `429 RATE_LIMITED` — 사용자당 분당 5번 넘게 새로 부름.
    - **상태:** `구현됨`.
    """
    cand = assignment_service._load_candidate(db, candidate_id)
    event = db.get(Event, cand.run.event_id)
    if not guest_service.is_manager(db, user, event.team_id):
        raise E.ForbiddenRole()
    return ai_service.explain_candidate(db, cand, user)


@router.get(
    "/events/{event_id}/assignment/adopted/ai-message", response_model=AiMessage,
    responses=errors(_403="NOT_A_MEMBER", _404="NOT_ADOPTED_YET", _429="RATE_LIMITED"), summary="AI 한마디 (팀원용)",
)
def ai_message(db: DB, user: CurrentUser, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)]):
    """확정된 배정에서 나에게 맞춘 2~3문장 안내 (LangChain · 체인 B).

    - **권한:** 그 일정 팀원. 배정에 들지 않았으면 `message=null`.
    - **처리:** 팀마다 한 번만 불러 그 팀 선수 전원의 문장을 받아 두고, 요청한 사람 것만 돌려준다. 실력 값은 보내지 않고,
      출력에 등급·점수·순위가 나오면 버린다. 실패하면 기존 팀원용 설명(`fallback=true`).
    - **상태:** `구현됨`.
    """
    player = db.get(Player, me.id) if me.id else me
    return ai_service.member_message(db, event, player, user)


@router.post(
    "/events/{event_id}/tactics/ai-recommend", response_model=AiTactics,
    responses=errors(_403=("NOT_A_MEMBER", "NOT_ATTENDEE"), _404=("NOT_ADOPTED_YET", "NOT_FOUND"), _429="RATE_LIMITED"),
    summary="AI 전술 추천 설명",
)
def ai_tactics(
    db: DB, user: CurrentUser, me: EventMember, event: Annotated[Event, Depends(get_event_or_404)],
    squad_no: Annotated[int, Query(description="팀 번호 (1 블랙 · 2 화이트)")],
    zone: Annotated[bool, Query(description="상대가 지역 수비를 쓰면 true")] = False,
):
    """한 팀의 추천 전술(규칙 기반 상위 3개)을 전술마다 이유 · 핵심 자리 · 주의점과 한 줄 요약으로 설명한다 (LangChain · 체인 C).

    - **권한:** 그 일정 참석자 · 매니저 · ADMIN.
    - **처리:** 추천 순서·전술·자리는 바꾸지 않는다. 입력에 없는 전술이 나오면 전부 버리고, 빠진 전술은 규칙 문장으로 채운다.
      같은 팀 · 같은 수비 보기면 저장해 둔 결과를 쓴다. 실패하면 `fallback=true` 와 규칙 문장("적합도 81 · 허재 볼 핸들러(볼 운반) …").
    - **오류:** `403 NOT_ATTENDEE`, `404 NOT_ADOPTED_YET`, `429 RATE_LIMITED`.
    - **상태:** `구현됨`. **설계서:** docs/07 FR-52.
    """
    player = db.get(Player, me.id) if me.id else me
    return ai_service.explain_tactics(db, event, player, user, squad_no=squad_no, zone=zone)
