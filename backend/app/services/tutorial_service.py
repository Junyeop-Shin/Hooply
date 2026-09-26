"""시작 안내(튜토리얼) — 상태 저장과 체크리스트 판정.

체크리스트는 "며칠 안에 끝나는 준비" 만 담는다. 배정·경기 기록·투표처럼 경기가 있어야 열리는 기능은 여기 넣지 않고,
그 화면에 처음 들어갔을 때 한 번 뜨는 안내(TIP_IDS)로 알려 준다 — 몇 주 동안 미완료로 떠 있는 카드는 결국 닫히기 때문.
단계 판정은 실제 데이터를 본다. 남의 행동이 먼저 필요한 단계(팀원 모집, 매니저의 일정 등록)는 WAITING 과 이유를 준다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core import errors
from app.core.config import get_settings
from app.models import Event, EventAttendance, Player, PlayerProfile, Team, User
from app.models.enums import (
    ApprovalStatus,
    EventStatus,
    PlayerKind,
    PlayerStatus,
    TeamRole,
    TeamStatus,
    TutorialPath,
    TutorialState,
)
from app.schemas.tutorial import TutorialStep, TutorialUpdate, TutorialView

# 기능별 첫 안내 — 화면 쪽 lib/tutorial-content.ts 의 키와 같아야 한다
TIP_IDS = frozenset({"assign", "quarters", "vote", "adopted", "records"})


def update(db: Session, user: User, body: TutorialUpdate) -> User:
    data = body.model_dump(exclude_unset=True)
    if "tip_seen" in data and data["tip_seen"] is not None:
        tip = data["tip_seen"]
        if tip not in TIP_IDS:
            raise errors.ValidationError(f"알 수 없는 안내예요: {tip}")
        if tip not in (user.tutorial_tips_seen or []):
            user.tutorial_tips_seen = [*(user.tutorial_tips_seen or []), tip]  # 새 리스트를 넣어야 JSONB 변경이 저장된다
    if data.get("state") is not None:
        user.tutorial_state = TutorialState(data["state"])
        if data["state"] == TutorialState.ACTIVE and "path" not in data:
            user.tutorial_path = None  # 다시 시작 → 경로 선택부터
    if "path" in data:
        user.tutorial_path = TutorialPath(data["path"]) if data["path"] else None
    db.commit()
    return user


def _now_local():
    return datetime.now(ZoneInfo(get_settings().timezone))


def _team_wait_reason(team: Team, members: int) -> str:
    if team.approval_status == ApprovalStatus.REJECTED:
        return "관리자가 팀 승인을 거절했어요. 도움말의 문의로 연락해 주세요."
    parts = []
    if team.approval_status == ApprovalStatus.PENDING:
        parts.append("관리자 승인 대기 중 (보통 하루 안)")
    if members < team.min_members:
        parts.append(f"팀원 {members}/{team.min_members}명")
    return " · ".join(parts) or "곧 활성화돼요"


def view(db: Session, user: User) -> TutorialView:
    base = TutorialView(state=str(user.tutorial_state), path=str(user.tutorial_path) if user.tutorial_path else None, tips_seen=list(user.tutorial_tips_seen or []))
    if user.tutorial_path is None:
        return base
    players = db.scalars(
        select(Player).where(Player.user_id == user.id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
        .options(selectinload(Player.team), selectinload(Player.profile)).order_by(Player.joined_at)
    ).all()
    survey = TutorialStep(
        key="SURVEY", title="실력·포지션 설문", status="DONE" if user.onboarding_completed else "TODO",
        hint="2분 정도 걸려요. 팀을 나눌 때 가장 먼저 쓰이는 정보예요.", link="/survey", action="설문하기",
    )
    steps: list[TutorialStep]
    if user.tutorial_path == TutorialPath.PLAYER:
        steps = [
            TutorialStep(key="JOIN_TEAM", title="팀 코드로 가입", status="DONE" if players else "TODO",
                         hint="매니저에게 받은 8자리 팀 코드를 넣어요. 코드가 없다면 매니저에게 받아 주세요.", link="/teams/join", action="코드 넣기"),
            survey,
            _self_rank_step(players),
            _rsvp_step(db, players),
        ]
    else:
        managed = [p for p in players if p.role == TeamRole.MANAGER]
        team = next((p.team for p in managed if p.team_id == user.primary_team_id), managed[0].team if managed else None)
        steps = [
            TutorialStep(key="CREATE_TEAM", title="팀 만들기", status="DONE" if managed else "TODO",
                         hint="팀 이름만 있으면 돼요. 만들면 팀원을 초대할 8자리 코드가 나와요.", link="/teams/new", action="팀 만들기"),
            survey,
            *_manager_team_steps(db, team),
        ]
    return base.model_copy(update={"steps": steps, "all_done": all(s.status == "DONE" for s in steps)})


def _self_rank_step(players: list[Player]) -> TutorialStep:
    title = "이 동호회에서 내 실력 위치"
    if not players:
        return TutorialStep(key="SELF_RANK", title=title, status="WAITING", hint="팀에 들어가면 열려요.")
    if any(p.profile and p.profile.self_rank_level for p in players):
        return TutorialStep(key="SELF_RANK", title=title, status="DONE", hint="팀 배정 정확도에 가장 큰 영향을 주는 한 문항이에요.")
    p = players[0]
    return TutorialStep(key="SELF_RANK", title=title, status="TODO", hint="팀 배정 정확도에 가장 큰 영향을 주는 한 문항이에요.",
                        link=f"/teams/{p.team_id}/self-rank", action="답하기")


def _rsvp_step(db: Session, players: list[Player]) -> TutorialStep:
    title = "첫 일정에 참석 응답"
    if not players:
        return TutorialStep(key="FIRST_RSVP", title=title, status="WAITING", hint="팀에 들어가면 열려요.")
    ids = [p.id for p in players]
    answered = db.scalar(
        select(func.count()).select_from(EventAttendance)
        .where(EventAttendance.player_id.in_(ids), EventAttendance.registered_by.is_(None), EventAttendance.responded_at.is_not(None))
    )
    if answered:
        return TutorialStep(key="FIRST_RSVP", title=title, status="DONE", hint="참석 여부는 마감 전까지 바꿀 수 있어요.")
    now = datetime.now(UTC)
    ev = db.scalars(
        select(Event).where(
            Event.team_id.in_([p.team_id for p in players]), Event.status == EventStatus.OPEN, Event.event_date >= _now_local().date(),
            or_(Event.rsvp_deadline.is_(None), Event.rsvp_deadline > now),
        ).order_by(Event.event_date, Event.start_time).limit(1)
    ).first()
    if ev:
        return TutorialStep(key="FIRST_RSVP", title=title, status="TODO",
                            hint=f"{ev.event_date.month}/{ev.event_date.day} {ev.title or '일정'}에 참석 또는 불참을 답해 주세요.",
                            link=f"/events/{ev.id}", action="응답하기")
    inactive = next((p.team for p in players if p.team.status != TeamStatus.ACTIVE), None)
    if inactive and len({p.team_id for p in players}) == 1:
        from app.services.team_service import member_count

        return TutorialStep(key="FIRST_RSVP", title=title, status="WAITING",
                            hint=f"팀이 활성화되면 매니저가 일정을 올려요. ({_team_wait_reason(inactive, member_count(db, inactive.id))})")
    return TutorialStep(key="FIRST_RSVP", title=title, status="WAITING", hint="매니저가 일정을 올리면 여기서 바로 응답할 수 있어요.")


def _manager_team_steps(db: Session, team: Team | None) -> list[TutorialStep]:
    invite_title, event_title = "팀원 초대 (5명 이상)", "첫 일정 등록"
    if team is None:
        return [
            TutorialStep(key="INVITE", title=invite_title, status="WAITING", hint="팀을 만들면 열려요."),
            TutorialStep(key="FIRST_EVENT", title=event_title, status="WAITING", hint="팀을 만들면 열려요."),
        ]
    from app.services.team_service import member_count

    members = member_count(db, team.id)
    active = team.status == TeamStatus.ACTIVE
    invite = TutorialStep(
        key="INVITE", title=invite_title, status="DONE" if active else "TODO",
        hint=f"팀이 활성화됐어요 · 팀원 {members}명" if active else f"팀 화면에서 코드를 카카오톡으로 공유해요. {_team_wait_reason(team, members)}",
        link=None if active else f"/teams/{team.id}", action=None if active else "코드 공유하기",
    )
    has_event = db.scalar(select(func.count()).select_from(Event).where(Event.team_id == team.id)) or 0
    if has_event:
        first = TutorialStep(key="FIRST_EVENT", title=event_title, status="DONE", hint="팀원들이 참석 응답을 하면 일정 화면에서 팀을 나눌 수 있어요.")
    elif not active:
        first = TutorialStep(key="FIRST_EVENT", title=event_title, status="WAITING", hint="팀이 활성화되면 열려요.")
    else:
        first = TutorialStep(key="FIRST_EVENT", title=event_title, status="TODO", hint="날짜·시간·장소만 넣으면 팀원들에게 참석 응답을 받을 수 있어요.",
                             link=f"/teams/{team.id}/events/new", action="일정 등록하기")
    return [invite, first]


_ = PlayerProfile  # 프로필은 selectinload 로만 쓴다 (import 유지용)
