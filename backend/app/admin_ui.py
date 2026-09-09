"""관리자 콘솔 (S-18) — SQLAdmin 을 `/admin` 에 붙인다 (11.2절 · 11.4절 "관리자 화면을 만들지 않는다").

- 로그인: 이메일/비밀번호 + `users.global_role = ADMIN` 인 계정만. 세션 쿠키는 JWT 비밀키로 서명한다.
- 조회·수정: 사용자·팀·참가자·프로필·일정·쿼터·투표·정렬·감사 로그. 지표 보정은 이력을 남겨야 하므로 API
  (`PATCH /api/v1/admin/players/{id}/rating`) 를 쓰고, 여기서는 player_profiles 를 읽기 전용으로 둔다.
- 프론트(nginx)는 /api 만 프록시하므로 콘솔은 백엔드 주소(예: http://localhost:8000/admin)로 직접 연다.
"""

from fastapi import FastAPI
from sqladmin import Admin, ModelView, action
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.core.config import get_settings
from app.core.security import verify_password
from app.db.session import SessionLocal, engine
from app.models import (
    AssignmentCandidate,
    AssignmentRun,
    AuditLog,
    Event,
    EventAttendance,
    ManagerRanking,
    Player,
    PlayerProfile,
    PostGameSurvey,
    PostGameVote,
    Quarter,
    QuarterLineup,
    SkillRatingHistory,
    Team,
    User,
)
from app.models.enums import GlobalRole


class AdminAuth(AuthenticationBackend):
    """SQLAdmin 로그인 — ADMIN 계정만. 세션에 user id 를 넣고 매 요청마다 권한을 다시 확인한다."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        email, password = str(form.get("username", "")).strip(), str(form.get("password", ""))
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
            if user is None or user.global_role != GlobalRole.ADMIN or not user.password_hash or not verify_password(password, user.password_hash):
                return False
            request.session.update({"admin_user_id": user.id})
            return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        uid = request.session.get("admin_user_id")
        if not uid:
            return False
        with SessionLocal() as db:
            user = db.get(User, uid)
            return bool(user and user.global_role == GlobalRole.ADMIN and user.deleted_at is None)


class UserAdmin(ModelView, model=User):
    name, name_plural, icon = "사용자", "사용자", "fa-solid fa-user"
    column_list = [User.id, User.email, User.name, User.nickname, User.global_role, User.onboarding_completed, User.created_at, User.deleted_at]
    column_searchable_list = [User.email, User.name, User.nickname]
    column_details_exclude_list = [User.password_hash]
    form_excluded_columns = [User.password_hash, User.created_at, User.updated_at]
    column_default_sort = (User.id, True)


class TeamAdmin(ModelView, model=Team):
    """팀 목록. 새 팀은 approval_status=PENDING 으로 들어오며 목록에서 체크 → '승인' 액션으로 활성화한다."""

    name, name_plural, icon = "팀", "팀", "fa-solid fa-people-group"
    column_list = [Team.id, Team.name, Team.team_code, Team.approval_status, Team.status, Team.owner_user_id, Team.home_court, Team.created_at]
    column_searchable_list = [Team.name, Team.team_code]
    column_default_sort = (Team.id, True)
    form_excluded_columns = [Team.players, Team.approved_at, Team.approved_by]

    async def _decide(self, request: Request, approved: bool):
        from app.models import AuditLog
        from app.services import team_service

        pks = [int(x) for x in request.query_params.get("pks", "").split(",") if x]
        admin_id = request.session.get("admin_user_id")
        with SessionLocal() as db:
            admin = db.get(User, admin_id) if admin_id else None
            for pk in pks:
                team = db.get(Team, pk)
                if team is None:
                    continue
                before = team.approval_status
                team_service.set_approval(db, team, admin, approved)
                db.add(AuditLog(actor_user_id=admin_id, action="TEAM_APPROVE" if approved else "TEAM_REJECT", target_type="team", target_id=team.id,
                                before={"approval_status": before}, after={"approval_status": team.approval_status, "status": team.status}))
                db.commit()
        return RedirectResponse(request.url_for("admin:list", identity=self.identity), status_code=302)

    @action(name="approve", label="승인", confirmation_message="선택한 팀을 승인할까요? 회원이 5명 이상이면 바로 활성화돼요.", add_in_detail=True, add_in_list=True)
    async def approve(self, request: Request):
        return await self._decide(request, True)

    @action(name="reject", label="승인 거절", confirmation_message="선택한 팀의 승인을 거절할까요?", add_in_detail=True, add_in_list=True)
    async def reject(self, request: Request):
        return await self._decide(request, False)


class PlayerAdmin(ModelView, model=Player):
    name, name_plural, icon = "참가자", "참가자", "fa-solid fa-basketball"
    column_list = [Player.id, Player.team_id, Player.user_id, Player.kind, Player.display_name, Player.role, Player.status, Player.height_cm, Player.merged_into_player_id, Player.joined_at]
    column_searchable_list = [Player.display_name]
    column_default_sort = (Player.id, True)


class ProfileAdmin(ModelView, model=PlayerProfile):
    name, name_plural, icon = "실력 프로필", "실력 프로필", "fa-solid fa-chart-line"
    can_create = can_edit = can_delete = False  # 보정은 이력을 남기는 API 로만
    column_list = [PlayerProfile.player_id, PlayerProfile.prior_overall, PlayerProfile.prior_source, PlayerProfile.skill_overall, PlayerProfile.skill_confidence, PlayerProfile.quarters_played, PlayerProfile.cumulative_residual, PlayerProfile.updated_at]


class EventAdmin(ModelView, model=Event):
    name, name_plural, icon = "일정", "일정", "fa-solid fa-calendar"
    column_list = [Event.id, Event.team_id, Event.title, Event.event_date, Event.start_time, Event.end_time, Event.status, Event.venue]
    column_default_sort = (Event.event_date, True)


class AttendanceAdmin(ModelView, model=EventAttendance):
    name, name_plural, icon = "참석 응답", "참석 응답", "fa-solid fa-clipboard-check"
    column_list = [EventAttendance.id, EventAttendance.event_id, EventAttendance.player_id, EventAttendance.status, EventAttendance.responded_at, EventAttendance.registered_by]


class QuarterAdmin(ModelView, model=Quarter):
    name, name_plural, icon = "쿼터", "쿼터", "fa-solid fa-stopwatch"
    column_list = [Quarter.id, Quarter.event_id, Quarter.quarter_no, Quarter.black_score, Quarter.white_score, Quarter.duration_min, Quarter.recorded_by]


class LineupAdmin(ModelView, model=QuarterLineup):
    name, name_plural, icon = "쿼터 출전", "쿼터 출전", "fa-solid fa-list"
    can_create = can_edit = can_delete = False  # 마진은 서버 계산값
    column_list = [QuarterLineup.id, QuarterLineup.quarter_id, QuarterLineup.player_id, QuarterLineup.side, QuarterLineup.position, QuarterLineup.raw_margin, QuarterLineup.normalized_margin]


class RunAdmin(ModelView, model=AssignmentRun):
    name, name_plural, icon = "배정 실행", "배정 실행", "fa-solid fa-shuffle"
    can_create = can_edit = False
    column_list = [AssignmentRun.id, AssignmentRun.event_id, AssignmentRun.executed_by, AssignmentRun.team_count, AssignmentRun.created_at]


class CandidateAdmin(ModelView, model=AssignmentCandidate):
    name, name_plural, icon = "배정 후보안", "배정 후보안", "fa-solid fa-table-list"
    can_create = can_edit = False
    column_list = [AssignmentCandidate.id, AssignmentCandidate.run_id, AssignmentCandidate.strategy, AssignmentCandidate.total_score, AssignmentCandidate.is_adopted]


class SurveyAdmin(ModelView, model=PostGameSurvey):
    name, name_plural, icon = "피어 투표 제출", "피어 투표 제출", "fa-solid fa-square-poll-horizontal"
    can_create = can_edit = False
    column_list = [PostGameSurvey.id, PostGameSurvey.event_id, PostGameSurvey.respondent_player_id, PostGameSurvey.submitted_at]


class VoteAdmin(ModelView, model=PostGameVote):
    name, name_plural, icon = "피어 투표 항목", "피어 투표 항목", "fa-solid fa-thumbs-up"
    can_create = can_edit = False
    column_list = [PostGameVote.id, PostGameVote.survey_id, PostGameVote.target_player_id, PostGameVote.vote_type, PostGameVote.target_side, PostGameVote.reason_tag]


class RankingAdmin(ModelView, model=ManagerRanking):
    name, name_plural, icon = "매니저 실력 정렬", "매니저 실력 정렬", "fa-solid fa-arrow-down-1-9"
    can_create = can_edit = False
    column_list = [ManagerRanking.id, ManagerRanking.team_id, ManagerRanking.ranked_by, ManagerRanking.is_active, ManagerRanking.created_at]


class HistoryAdmin(ModelView, model=SkillRatingHistory):
    name, name_plural, icon = "실력값 변동 이력", "실력값 변동 이력", "fa-solid fa-clock-rotate-left"
    can_create = can_edit = can_delete = False
    column_list = [SkillRatingHistory.id, SkillRatingHistory.player_id, SkillRatingHistory.source, SkillRatingHistory.before_value, SkillRatingHistory.after_value, SkillRatingHistory.delta, SkillRatingHistory.reason, SkillRatingHistory.created_at]
    column_default_sort = (SkillRatingHistory.id, True)


class AuditAdmin(ModelView, model=AuditLog):
    name, name_plural, icon = "감사 로그", "감사 로그", "fa-solid fa-shield-halved"
    can_create = can_edit = can_delete = False
    column_list = [AuditLog.id, AuditLog.actor_user_id, AuditLog.action, AuditLog.target_type, AuditLog.target_id, AuditLog.reason, AuditLog.created_at]
    column_default_sort = (AuditLog.id, True)


def mount_admin(app: FastAPI) -> None:
    settings = get_settings()
    admin = Admin(app, engine, base_url="/admin", title="HOOPLY 관리자", authentication_backend=AdminAuth(secret_key=settings.jwt_secret_key, https_only=settings.admin_cookie_secure, same_site="lax"))
    for view in (UserAdmin, TeamAdmin, PlayerAdmin, ProfileAdmin, EventAdmin, AttendanceAdmin, QuarterAdmin, LineupAdmin, RunAdmin, CandidateAdmin, SurveyAdmin, VoteAdmin, RankingAdmin, HistoryAdmin, AuditAdmin):
        admin.add_view(view)
