"""7.3절 관리자 — 사용자 검색, 선수 원시 데이터, 지표 수동 보정, 감사 로그 (F12).

일반 CRUD 화면(S-18)은 SQLAdmin(`/admin`, app/admin_ui.py)이 대신하므로, 여기에는 SQLAdmin으로 표현하기 어려운
원시 데이터 열람과 이력을 남기는 보정 API만 둔다. 모든 엔드포인트는 전역 `ADMIN`만 호출할 수 있다.

설계서: 7.3절 관리자, FR-32, 3.2절 관리자 기능, 6.2절 `skill_rating_history` / `audit_logs`, 11.2절 SQLAdmin.

엔드포인트
- GET   /admin/users                        전체 사용자 검색·페이징 (구현됨)
- GET   /admin/players/{player_id}/raw      선수 원시 데이터 전체 (구현됨)
- PATCH /admin/players/{player_id}/rating   실력 지표 수동 보정 (구현됨)
- GET   /admin/audit-logs                   감사 로그 (구현됨)
- GET   /admin/teams                        승인 대기/전체 팀 목록 (구현됨)
- POST  /admin/teams/{team_id}:approve      팀 승인 · :reject 거절 (구현됨, 감사 로그 기록)
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, AdminUser
from app.api.v1._docs import errors
from app.core import errors as E
from app.db.session import lock_team_stats
from app.models import (
    AuditLog,
    Player,
    PostGameSurvey,
    PostGameVote,
    Quarter,
    QuarterLineup,
    SkillRatingHistory,
    SurveyResponse,
    Team,
    User,
)
from app.models.enums import RatingSource
from app.schemas.admin import AdminUserRow, AuditLogView, PlayerRawData, RatingAdjust
from app.schemas.common import ItemList, Page, PageMeta, PlayerCardDetailed
from app.schemas.team import TeamDetail, UserSummary
from app.services import player_service, rating_service, team_service

router = APIRouter(prefix="/admin", tags=["관리자"])


def _row(obj: Any) -> dict[str, Any]:
    """ORM 행 → 컬럼 dict (관계 제외). 원시 데이터 덤프용."""
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


@router.get("/users", response_model=Page[AdminUserRow], summary="전체 사용자 검색")
def list_users(
    db: DB, admin: AdminUser,
    q: Annotated[str | None, Query(description="이름·닉네임·이메일 부분 일치 검색어. 생략 시 전체")] = None,
    page: Annotated[int, Query(ge=1, description="페이지 번호 (1부터, 기본 1)")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="페이지 크기 (기본 20)")] = 20,
):
    """전체 로그인 계정을 검색어·페이지로 조회한다 (탈퇴 계정 포함).

    - **권한:** ADMIN (전역 권한).
    - **처리:** `users` 를 이름·닉네임·이메일 부분 일치로 검색해 최신 가입순으로 페이징한다. 동일인 중복 가입
      (`POSSIBLE_DUPLICATE`) 조사에 쓴다. 비밀번호 해시는 내려가지 않는다.
    - **오류:** `403 FORBIDDEN_ROLE` — ADMIN이 아님. `401 TOKEN_EXPIRED`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /admin/users`), FR-32, F12, 3.2절 관리자, S-18.
    """
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.name.ilike(like), User.nickname.ilike(like), User.email.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size)).all()
    return Page(items=rows, meta=PageMeta(page=page, size=size, total=total, has_next=page * size < total))


@router.get("/players/{player_id}/raw", response_model=PlayerRawData, responses=errors(_403="FORBIDDEN_ROLE"), summary="선수 원시 데이터 열람")
def player_raw(db: DB, admin: AdminUser, player_id: int):
    """특정 참가자의 원시 데이터 전체 — 설문 응답, 쿼터별 마진, 투표 수신, 지표 변동 이력.

    - **권한:** ADMIN.
    - **처리:** `players` 행, `player_profiles`, 설문 응답 원본(회원이면 계정 기준), `quarter_lineups` 전체,
      `post_game_votes` 수신 내역, `skill_rating_history` 를 한 응답으로 모은다. 다른 어떤 역할에게도 노출되지 않는
      유일한 원시 뷰다.
    - **오류:** `404 NOT_FOUND` — 참가자 없음. `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /admin/players/{player_id}/raw`), FR-32, 3.3절 "선수 상세 데이터 조회 — ADMIN ○ (원시)".
    """
    player = db.get(Player, player_id, options=[selectinload(Player.profile)])
    if player is None:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    answers: list[dict[str, Any]] = []
    if player.user_id:
        for resp in db.scalars(select(SurveyResponse).where(SurveyResponse.user_id == player.user_id).options(selectinload(SurveyResponse.answers))).all():
            answers.extend({**_row(a), "template_id": resp.template_id, "submitted_at": resp.submitted_at} for a in resp.answers)
    lineups = [
        {**_row(lu), "event_id": q.event_id, "quarter_no": q.quarter_no, "black_score": q.black_score, "white_score": q.white_score, "duration_min": q.duration_min}
        for lu, q in db.execute(select(QuarterLineup, Quarter).join(Quarter, Quarter.id == QuarterLineup.quarter_id).where(QuarterLineup.player_id == player.id).order_by(Quarter.id)).all()
    ]
    votes = [
        {**_row(v), "event_id": s.event_id, "respondent_player_id": s.respondent_player_id, "submitted_at": s.submitted_at}
        for v, s in db.execute(select(PostGameVote, PostGameSurvey).join(PostGameSurvey, PostGameSurvey.id == PostGameVote.survey_id).where(PostGameVote.target_player_id == player.id)).all()
    ]
    history = [_row(h) for h in db.scalars(select(SkillRatingHistory).where(SkillRatingHistory.player_id == player.id).order_by(SkillRatingHistory.id)).all()]
    return PlayerRawData(
        player=_row(player), profile=_row(player.profile) if player.profile else None,
        survey_answers=answers, lineups=lineups, votes_received=votes, rating_history=history,
    )


def _s(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


@router.patch("/players/{player_id}/rating", response_model=PlayerCardDetailed, responses=errors(_403="FORBIDDEN_ROLE"), summary="실력 지표 수동 보정")
def adjust_rating(db: DB, admin: AdminUser, player_id: int, body: RatingAdjust):
    """참가자의 종합 실력값을 사유와 함께 직접 보정한다.

    - **권한:** ADMIN.
    - **처리:** 재계산의 출발점(사전값 + `player_profiles.admin_adjust`)을 옮겨 `skill_overall` 이 `body.skill_overall` 이
      되게 한다. 사전값 `prior_overall` 은 건드리지 않는다 — 설문 · 정렬 재계산이 사전값을 다시 써도 오프셋은 남고,
      쿼터를 다시 재생해도 출발점에 한 번만 더해진다(두 번 반영되지 않는다). 경기 기록이 쌓이면 다른 사전 정보처럼 실측에
      묻혀 간다. `skill_rating_history(source=ADMIN_ADJUST)` 와 `audit_logs` 에 누가·언제·왜 바꿨는지 남긴다.
      보정 대상의 이력은 ADMIN_ADJUST 한 줄뿐이고, 재생의 여파로 값이 바뀐 다른 선수에게는 "관리자 보정(선수 N) 재계산"
      이력이 남는다. 그 인원수는 감사 로그 `after.affected_players` 에 적는다.
    - **오류:** `404 NOT_FOUND`, `403 FORBIDDEN_ROLE`, `400 VALIDATION_ERROR` — 사유 누락, 경기 기록과 너무 멀어
      오프셋이 ±50점을 넘어야 하는 값.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`PATCH /admin/players/{player_id}/rating`), FR-32, 6.2절 `skill_rating_history` · `audit_logs`.
    """
    player = db.get(Player, player_id, options=[selectinload(Player.profile), selectinload(Player.positions)])
    if player is None or player.profile is None:
        raise E.NotFound("이 사람을 찾을 수 없어요.")
    prof = player.profile
    before_skill = prof.skill_overall
    before = {"skill_overall": _s(prof.skill_overall), "admin_adjust": _s(prof.admin_adjust)}
    target = round(float(body.skill_overall), 1)
    lock_team_stats(db, player.team_id)  # 프로필을 쓰기 전에 팀 잠금 (quarter_service 모듈 docstring 의 잠금 순서)
    prof.admin_adjust = rating_service.admin_adjust_for(db, player, target)
    db.flush()
    # 경기 기록이 없으면 skill_overall = prior + admin_adjust. 대상 본인의 RESIDUAL 이력은 만들지 않고(아래 ADMIN_ADJUST 한 줄만),
    # 여파로 바뀐 다른 선수에게는 "관리자 보정(선수 N) 재계산" 이력을 남긴다
    result = rating_service.recompute_team(db, player.team_id, cause="admin_adjust", cause_player_id=player.id)
    after_v = prof.skill_overall
    affected = result["changed_players"]  # 대상 본인을 뺀, 여파로 값이 바뀐 인원
    db.add(SkillRatingHistory(
        player_id=player.id, source=RatingSource.ADMIN_ADJUST, before_value=before_skill, after_value=after_v,
        delta=(after_v or Decimal(0)) - (before_skill or Decimal(0)), ref_type="admin_user", ref_id=admin.id, reason=body.reason,
    ))
    prof.updated_at = datetime.now(UTC)
    db.add(AuditLog(
        actor_user_id=admin.id, action="ADMIN_RATING_ADJUST", target_type="player", target_id=player.id,
        before=before,
        after={"skill_overall": _s(after_v), "admin_adjust": _s(prof.admin_adjust), "requested": str(target), "affected_players": affected},
        reason=body.reason,
    ))
    db.commit()
    db.refresh(player)
    return player_service.to_card_detailed(player)


@router.get("/audit-logs", response_model=Page[AuditLogView], summary="감사 로그 조회")
def audit_logs(
    db: DB, admin: AdminUser,
    page: Annotated[int, Query(ge=1, description="페이지 번호 (1부터, 기본 1)")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="페이지 크기 (기본 20)")] = 20,
):
    """관리자 보정·계정 정지·팀 비활성화 등 민감 조작의 이력을 최신순으로 조회한다.

    - **권한:** ADMIN.
    - **처리:** `audit_logs` 를 `id` 내림차순으로 페이징한다.
    - **오류:** `403 FORBIDDEN_ROLE`.
    - **상태:** `구현됨`.
    - **설계서:** 7.3절 (`GET /admin/audit-logs`), 6.1절 운영 그룹 `audit_logs`.
    """
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)).all()
    return Page(items=rows, meta=PageMeta(page=page, size=size, total=total, has_next=page * size < total))


def _team_detail(db, team: Team) -> TeamDetail:
    return TeamDetail(
        id=team.id, name=team.name, description=team.description, team_code=team.team_code, status=team.status,
        approval_status=team.approval_status, min_members=team.min_members, home_court=team.home_court,
        owner=UserSummary.model_validate(db.get(User, team.owner_user_id)), member_count=team_service.member_count(db, team.id),
        created_at=team.created_at,
    )


@router.get("/teams", response_model=ItemList[TeamDetail], summary="팀 목록 (승인 대기 우선)")
def list_teams(
    db: DB, admin: AdminUser,
    approval: Annotated[str | None, Query(description="PENDING / APPROVED / REJECTED 필터. 생략 시 전체")] = None,
):
    """전체 팀을 승인 상태로 걸러 본다. 기본은 전체, 승인 대기가 위로 온다.

    - **권한:** ADMIN.
    - **상태:** `구현됨`.
    """
    stmt = select(Team)
    if approval:
        stmt = stmt.where(Team.approval_status == approval)
    rows = db.scalars(stmt.order_by((Team.approval_status == "PENDING").desc(), Team.id.desc())).all()
    return ItemList(items=[_team_detail(db, t) for t in rows])


def _decide(db, admin: User, team_id: int, approved: bool) -> TeamDetail:
    team = db.get(Team, team_id)
    if team is None:
        raise E.NotFound("팀을 찾을 수 없어요.")
    before = team.approval_status
    team_service.set_approval(db, team, admin, approved)
    db.add(AuditLog(
        actor_user_id=admin.id, action="TEAM_APPROVE" if approved else "TEAM_REJECT", target_type="team", target_id=team.id,
        before={"approval_status": before}, after={"approval_status": team.approval_status, "status": team.status}, reason=None,
    ))
    db.commit()
    return _team_detail(db, team)


@router.post("/teams/{team_id}:approve", response_model=TeamDetail, summary="팀 승인")
def approve_team(db: DB, admin: AdminUser, team_id: int):
    """팀을 승인한다. 회원이 5명 이상이면 바로 ACTIVE 가 되고 일정 기능이 열린다. `audit_logs` 에 남긴다.

    - **권한:** ADMIN. **상태:** `구현됨`.
    """
    return _decide(db, admin, team_id, True)


@router.post("/teams/{team_id}:reject", response_model=TeamDetail, summary="팀 승인 거절")
def reject_team(db: DB, admin: AdminUser, team_id: int):
    """팀 승인을 거절한다. 팀은 남지만 활성화되지 않는다. 다시 승인하면 되돌릴 수 있다.

    - **권한:** ADMIN. **상태:** `구현됨`.
    """
    return _decide(db, admin, team_id, False)
