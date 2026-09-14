"""데모 데이터 삭제 — seed_demo 가 만든 계정(@demo.com)·팀·그 팀의 일정/기록/투표만 지운다. 다른 데이터는 건드리지 않는다.

운영 DB 에서 테스트가 끝난 뒤 쓰는 용도:
  DATABASE_URL=postgresql+psycopg://... python -m scripts.remove_demo [--yes]

지우는 범위
- users: 이메일이 @demo.com 으로 끝나는 계정 (관리자 admin@demo.com 포함) 과 그 로그인 수단·설문 응답
- teams: 위 계정이 만든 팀 + 데모 팀 이름 3개 → 참가자(게스트 포함)·프로필·일정·참석·배정·쿼터·투표·정렬·초대 이력 전부 (FK CASCADE)
- chemistry_scores / 감사 로그의 actor 참조처럼 CASCADE 가 없는 곳은 먼저 정리한다
데모 팀에 팀 코드로 들어온 실제 계정은 계정은 남고 그 팀 소속만 사라진다.
"""

from __future__ import annotations

import sys

from sqlalchemy import delete, or_, select, text, update

from app.db.session import SessionLocal
from app.models import (
    AssignmentConstraint,
    AssignmentSlot,
    AuditLog,
    ChemistryScore,
    Event,
    EventAttendance,
    ManagerRankingEntry,
    Player,
    PostGameSurvey,
    PostGameVote,
    QuarterLineup,
    SurveyResponse,
    Team,
    User,
)
from app.models.enums import PlayerKind

DEMO_TEAM_NAMES = ("일요 코트메이트", "수요 픽업", "목요 픽업")


def _detach_from_other_teams(db, demo_users: list[int], demo_teams: list[int]) -> None:
    """데모 계정이 데모 아닌 팀에 남긴 참가자 행을 정리한다.

    계정을 지우면 그 행이 FK 로 걸려 삭제가 통째로 실패한다. 경기·투표·배정 기록이 있으면 계정만
    떼어 내 게스트 행으로 남기고(그 팀 기록을 잃지 않도록), 기록이 없으면 딸린 행과 함께 지운다.
    """
    rows = db.scalars(
        select(Player).where(Player.user_id.in_(demo_users), Player.team_id.not_in(demo_teams or [-1]))
    ).all()
    for p in rows:
        keeps = (
            db.scalar(select(QuarterLineup.id).where(QuarterLineup.player_id == p.id).limit(1))
            or db.scalar(select(PostGameVote.id).where(PostGameVote.target_player_id == p.id).limit(1))
            or db.scalar(select(PostGameSurvey.id).where(PostGameSurvey.respondent_player_id == p.id).limit(1))
            or db.scalar(select(AssignmentSlot.id).where(AssignmentSlot.player_id == p.id).limit(1))
        )
        if keeps:
            p.user_id, p.kind = None, PlayerKind.GUEST  # CHECK (kind='GUEST') = (user_id IS NULL)
            print(f"  · 팀 {p.team_id} 의 '{p.display_name}' 는 기록이 있어 게스트 행으로 남깁니다")
            continue
        # 기록이 없으면 CASCADE 가 걸리지 않은 참조부터 지운다
        db.execute(update(EventAttendance).where(EventAttendance.team_lock_request_player_id == p.id).values(team_lock_request_player_id=None))
        db.execute(delete(EventAttendance).where(EventAttendance.player_id == p.id))
        db.execute(delete(ManagerRankingEntry).where(ManagerRankingEntry.player_id == p.id))
        db.execute(delete(AssignmentConstraint).where(AssignmentConstraint.player_id == p.id))
        db.execute(update(Player).where(Player.merged_into_player_id == p.id).values(merged_into_player_id=None))
        db.delete(p)
        print(f"  · 팀 {p.team_id} 의 '{p.display_name}' 참가자 행 삭제 (기록 없음)")
    db.flush()


def main() -> None:
    with SessionLocal() as db:
        demo_users = db.scalars(select(User.id).where(User.email.like("%@demo.com"))).all()
        demo_teams = db.scalars(select(Team.id).where(or_(Team.owner_user_id.in_(demo_users or [-1]), Team.name.in_(DEMO_TEAM_NAMES)))).all()
        demo_players = db.scalars(select(Player.id).where(Player.team_id.in_(demo_teams or [-1]))).all()
        print(f"삭제 대상: 계정 {len(demo_users)}개 · 팀 {len(demo_teams)}개 · 참가자 행 {len(demo_players)}개")
        if not demo_users and not demo_teams:
            print("지울 데모 데이터가 없어요.")
            return
        if "--yes" not in sys.argv:
            ans = input("계속할까요? (yes 입력) ")
            if ans.strip().lower() != "yes":
                print("취소했어요.")
                return
        demo_events = db.scalars(select(Event.id).where(Event.team_id.in_(demo_teams or [-1]))).all()
        if demo_players:
            db.execute(delete(ChemistryScore).where(or_(ChemistryScore.player_a_id.in_(demo_players), ChemistryScore.player_b_id.in_(demo_players))))
        if demo_events:
            # 투표·설문은 events 에서 CASCADE 되지 않고 players 를 참조하므로 먼저 지운다
            db.execute(delete(PostGameSurvey).where(PostGameSurvey.event_id.in_(demo_events)))  # votes 는 surveys 에서 CASCADE
            db.execute(delete(Event).where(Event.id.in_(demo_events)))  # 참석·쿼터·배정은 CASCADE
        if demo_users:
            _detach_from_other_teams(db, demo_users, demo_teams)
            db.execute(update(AuditLog).where(AuditLog.actor_user_id.in_(demo_users)).values(actor_user_id=None))
            db.execute(delete(SurveyResponse).where(SurveyResponse.user_id.in_(demo_users)))
            db.execute(update(User).where(User.primary_team_id.in_(demo_teams or [-1])).values(primary_team_id=None))
        if demo_teams:
            db.execute(delete(Team).where(Team.id.in_(demo_teams)))  # players·events·quarters·votes·rankings 는 CASCADE
        if demo_users:
            db.execute(delete(User).where(User.id.in_(demo_users)))  # auth_identities·presets 는 CASCADE
        db.commit()
        left = db.execute(text("select (select count(*) from users), (select count(*) from teams), (select count(*) from players)")).one()
        print(f"삭제 완료. 남은 데이터: 계정 {left[0]} · 팀 {left[1]} · 참가자 {left[2]}")


if __name__ == "__main__":
    main()
