"""데모 데이터 시드 — 20명 동호회 + 이번 주 일요일 일정 + 참석/게스트.

실행
  cd backend && uv run python -m scripts.seed_demo          # 로컬
  docker compose exec api python -m scripts.seed_demo       # 도커

만드는 것
  - 팀 "일요 코트메이트" (회원 20명, 전원 설문 v2 + 팀 내 자기 위치 응답 완료 → 실력 등급 계산됨)
  - 매니저 1명: manager@demo.com / demo1234  (이름 허재)
  - 팀원 19명: m01@demo.com ~ m19@demo.com / demo1234
  - 지난주 일요일 일정 1건 (종료됨): 회원 12명 참석 + 게스트 3명, 배정 확정까지 완료
      · 문경은(m04) 이 "게스트 허웅" 초대 · 김선형(m07) 이 "게스트 허훈" 초대 · 허재가 "게스트 송교창" 초대
      → 이번 주 일정의 게스트 초대 시트에서 "이전에 초대한 사람 불러오기" 로 확인 가능
  - 이번 주 일요일 일정 1건 (응답 마감 토요일 22:00). 회원 12명 참석, 3명 불참, 나머지 미응답
  - 이번 주 게스트 2명 참석: "게스트 허웅"(문경은 초대, 등급 4, 같은 팀 요청) · "게스트 이승현"(문경은 초대, 등급 미지정)
  이미 팀이 있으면 아무것도 만들지 않고 계정 정보만 출력한다 (멱등).

서비스 함수를 그대로 호출하므로 API 로 만든 것과 같은 상태가 된다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from pydantic import SecretStr
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Team, User
from app.models.enums import (
    AttendanceStatus,
    EventStatus,
    GlobalRole,
    Position,
    SelfRankLevel,
    Side,
)
from app.schemas.assignment import AssignmentRunRequest, ConstraintSet
from app.schemas.auth import SignupRequest
from app.schemas.event import EventCreate, EventGuestCreate
from app.schemas.game import LineupIn, QuarterBulkSave, QuarterIn
from app.schemas.peer import PostGameSurveyIn, VoteIn
from app.schemas.survey import SurveyAnswerIn, SurveyResponseIn
from app.schemas.team import TeamCreate
from app.services import (
    assignment_service,
    auth_service,
    event_service,
    peer_service,
    quarter_service,
    survey_service,
    team_service,
)
from app.services.guest_service import caller_player

TEAM2_NAME = "수요 픽업"
ADMIN_EMAIL = "admin@demo.com"
TEAM_NAME = "일요 코트메이트"
PASSWORD = "demo1234"
MANAGER_EMAIL = "manager@demo.com"

# (이름, 키, 자기 위치, 선호 포지션 순서, 1번 D3A, 5번 D3B, 경기 수준, 슛 거리, 볼 운반, 수비1, 수비2, 성향, 체력, 공격 옵션)
# 포지션이 골고루 섞이고 실력이 갈리도록 구성. 앞 12명이 이번 주 참석자.
ROSTER = [
    ("허재", 180, "TOP30", ["PG", "SG"], "CAN_PREFER", "CANNOT", "CLUB", "THREE", "HALF_COURT", "SWITCH", "HELP_RECOVER", "ONBALL", "Q3_4", ["PNR_HANDLER", "PULLUP", "DRIVE_FINISH"]),
    ("서장훈", 192, "TOP10", ["C", "PF"], "CANNOT", "CAN_PREFER", "AMATEUR", "FLOATER", "LIGHT_PRESS", "READ", "ROTATE_EARLY", "OFFBALL", "FULL", ["POST_UP", "PNR_ROLL_POP", "PUTBACK"]),
    ("이상민", 176, "TOP10", ["PG"], "CAN_PREFER", "CANNOT", "PRO", "DEEP_THREE", "FULL_COURT", "READ", "ROTATE_EARLY", "ONBALL", "FULL", ["PNR_HANDLER", "PULLUP", "CATCH_SHOOT", "DRIVE_FINISH"]),
    ("현주엽", 185, "TOP30", ["SF", "PF"], "CANNOT", "CAN_NO_PREFER", "AMATEUR", "THREE", "HALF_COURT", "SWITCH", "HELP_RECOVER", "MOSTLY_OFFBALL", "Q3_4", ["CATCH_SHOOT", "OFFBALL_CUT", "DRIVE_FINISH"]),
    ("문경은", 178, "MID", ["SG", "SF"], "CAN_NO_PREFER", "CANNOT", "CLUB", "THREE", "LIGHT_PRESS", "CHASE", "HELP_NO_RECOVER", "MOSTLY_OFFBALL", "Q3_4", ["CATCH_SHOOT", "OFFBALL_CUT"]),
    ("김주성", 190, "MID", ["PF", "C"], "CANNOT", "CAN_PREFER", "CLUB", "FLOATER", "NO_DRIVE", "SWITCH", "HELP_RECOVER", "OFFBALL", "Q2", ["POST_UP", "PUTBACK"]),
    ("양동근", 174, "MID", ["PG", "SG"], "CAN_NO_PREFER", "CANNOT", "STREET", "FT_LINE", "HALF_COURT", "CHASE", "HELP_NO_RECOVER", "MOSTLY_ONBALL", "Q3_4", ["DRIVE_FINISH", "PNR_HANDLER"]),
    ("김선형", 183, "MID", ["SF"], "CANNOT", "CANNOT", "CLUB", "THREE", "LIGHT_PRESS", "SWITCH", "HELP_NO_RECOVER", "MOSTLY_OFFBALL", "Q3_4", ["CATCH_SHOOT", "PULLUP"]),
    ("오세근", 188, "BOT30", ["PF", "SF"], "CANNOT", "CAN_NO_PREFER", "STREET", "FLOATER", "NO_DRIVE", "CHASE", "OWN_ONLY", "OFFBALL", "Q2", ["PUTBACK", "OFFBALL_CUT"]),
    ("김승현", 172, "BOT30", ["SG"], "CANNOT", "CANNOT", "PE", "FT_LINE", "LIGHT_PRESS", "UNAWARE", "OWN_ONLY", "MOSTLY_OFFBALL", "Q2", ["CATCH_SHOOT"]),
    ("하승진", 195, "BOT30", ["C"], "CANNOT", "CAN_NO_PREFER", "STREET", "LAYUP", "NO_DRIVE", "CHASE", "HELP_NO_RECOVER", "OFFBALL", "Q1", ["PUTBACK", "POST_UP"]),
    ("조성원", 177, "BOT10", ["SF", "SG"], "CANNOT", "CANNOT", "PE", "FT_LINE", "NO_DRIVE", "UNAWARE", "OWN_ONLY", "OFFBALL", "Q2", ["OFFBALL_CUT"]),
    # ── 여기까지 12명 참석 ──
    ("추승균", 181, "TOP30", ["SG", "SF"], "CAN_NO_PREFER", "CANNOT", "AMATEUR", "THREE", "HALF_COURT", "SWITCH", "HELP_RECOVER", "MOSTLY_ONBALL", "FULL", ["PULLUP", "DRIVE_FINISH", "CATCH_SHOOT"]),  # 불참
    ("우지원", 186, "MID", ["PF"], "CANNOT", "CAN_NO_PREFER", "CLUB", "FLOATER", "LIGHT_PRESS", "SWITCH", "HELP_RECOVER", "OFFBALL", "Q3_4", ["POST_UP", "PUTBACK"]),  # 불참
    ("전희철", 175, "BOT30", ["PG"], "CAN_NO_PREFER", "CANNOT", "STREET", "FT_LINE", "LIGHT_PRESS", "CHASE", "HELP_NO_RECOVER", "MOSTLY_ONBALL", "Q2", ["DRIVE_FINISH"]),  # 불참
    ("강동희", 179, "MID", ["SF", "SG"], "CANNOT", "CANNOT", "CLUB", "THREE", "LIGHT_PRESS", "CHASE", "HELP_RECOVER", "MOSTLY_OFFBALL", "Q3_4", ["CATCH_SHOOT", "OFFBALL_CUT"]),  # 미응답
    ("김유택", 184, "MID", ["PF", "SF"], "CANNOT", "CAN_NO_PREFER", "CLUB", "FT_LINE", "LIGHT_PRESS", "SWITCH", "HELP_NO_RECOVER", "OFFBALL", "Q3_4", ["PUTBACK", "OFFBALL_CUT"]),  # 미응답
    ("한기범", 171, "BOT10", ["PG", "SG"], "CAN_NO_PREFER", "CANNOT", "PE", "LAYUP", "LIGHT_PRESS", "UNAWARE", "OWN_ONLY", "MOSTLY_ONBALL", "Q1", ["DRIVE_FINISH"]),  # 미응답
    ("이충희", 189, "TOP30", ["C", "PF"], "CANNOT", "CAN_PREFER", "AMATEUR", "FLOATER", "LIGHT_PRESS", "READ", "HELP_RECOVER", "OFFBALL", "FULL", ["POST_UP", "PNR_ROLL_POP", "PUTBACK"]),  # 미응답
    ("주희정", 180, "MID", ["SG", "SF", "PG"], "CAN_NO_PREFER", "CANNOT", "CLUB", "THREE", "HALF_COURT", "SWITCH", "HELP_RECOVER", "MOSTLY_ONBALL", "Q3_4", ["CATCH_SHOOT", "PULLUP", "PNR_HANDLER"]),  # 미응답
]
ATTEND, ABSENT = 12, 3


def _answers(tpl, row) -> list[SurveyAnswerIn]:
    (_name, _h, _lvl, prefs, pg, c, a3, b2, b3, c1, c2, e1, e2, b1) = row
    pick = {"A2": ["Y3_7"], "A3": [a3], "B1": b1, "B2": [b2], "B3": [b3], "C1": [c1], "C2": [c2], "D1": prefs, "D3A": [pg], "D3B": [c], "E1": [e1], "E2": [e2]}
    out = []
    for q in tpl.questions:
        by_code = {o.code: o.id for o in q.options}
        out.append(SurveyAnswerIn(question_id=q.id, selected_option_ids=[by_code[x] for x in pick[q.code]]))
    return out


def next_sunday(today: date | None = None) -> date:
    """이번 주 일요일 (오늘이 일요일이면 오늘)."""
    today = today or datetime.now(UTC).astimezone().date()
    return today + timedelta(days=(6 - today.weekday()) % 7)


def reset_db() -> None:
    """설문 템플릿을 제외한 전 테이블을 비운다 (`--reset`). tests/conftest 와 같은 방식."""
    from sqlalchemy import text

    from app.db.session import engine
    from app.db.survey_seed import seed_active_survey
    from app.models import Base

    keep = {"survey_templates", "survey_questions", "survey_options"}
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables) if t.name not in keep)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        seed_active_survey(conn)
    print("기존 데이터를 모두 지웠어요.")


def _is_local_db() -> bool:
    from urllib.parse import urlsplit

    from app.core.config import get_settings

    return (urlsplit(get_settings().database_url).hostname or "") in ("localhost", "127.0.0.1", "db")


def main() -> None:
    import sys

    no_admin = "--no-admin" in sys.argv  # 운영 DB 에 올릴 때: admin@demo.com(고정 비밀번호 관리자) 을 만들지 않는다
    if "--reset" in sys.argv:
        if not _is_local_db() and "--i-really-mean-it" not in sys.argv:
            print("--reset 은 로컬 DB 에서만 허용해요. 운영 DB 의 데모 데이터만 지우려면 scripts.remove_demo 를 쓰세요.")
            sys.exit(2)
        reset_db()
    db = SessionLocal()
    try:
        if db.scalar(select(Team).where(Team.name == TEAM_NAME)):
            print(f"이미 '{TEAM_NAME}' 팀이 있어요. 매니저 계정: {MANAGER_EMAIL} / {PASSWORD}  (다시 만들려면 --reset)")
            return
        tpl = survey_service.get_active_template(db)

        # 1) 계정 + 설문
        users: list[User] = []
        for i, row in enumerate(ROSTER):
            email = MANAGER_EMAIL if i == 0 else f"m{i:02d}@demo.com"
            auth_service.signup(db, SignupRequest(email=email, password=SecretStr(PASSWORD), name=row[0], height_cm=row[1]))
            user = db.scalar(select(User).where(User.email == email))
            survey_service.submit(db, user, SurveyResponseIn(template_id=tpl.id, answers=_answers(tpl, row)))
            users.append(user)

        # 1-b) 관리자 계정 — SQLAdmin(/admin)·관리자 API 확인용. 팀에는 속하지 않는다 (--no-admin 이면 건너뜀)
        admin = None
        if not no_admin:
            auth_service.signup(db, SignupRequest(email=ADMIN_EMAIL, password=SecretStr(PASSWORD), name="관리자"))
            admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
            admin.global_role = GlobalRole.ADMIN
            db.commit()

        # 2) 팀 + 가입 + 자기 위치
        manager = users[0]
        team = team_service.create_team(db, manager, TeamCreate(name=TEAM_NAME, description="매주 일요일 오전, 게스트 환영", home_court="서초 사회체육관"))
        team_service.set_approval(db, team, admin, True)  # 관리자 승인 (콘솔에서 하는 것과 같은 처리)
        for u in users[1:]:
            team_service.join_team(db, u, team.team_code)
        for u, row in zip(users, ROSTER, strict=True):
            player = caller_player(db, u, team.id)
            survey_service.set_self_rank(db, player, SelfRankLevel(row[2]))

        players = [caller_player(db, u, team.id) for u in users]

        sunday = next_sunday()

        # 2-b) 지난 5주 ~ 2주 전 일정 4개 — 회원 12명 참석, 배정 확정, 쿼터 8개씩. 세 번째 회차부터 실력 지표에 반영된다
        #      (기록이 많은 사람: 매니저·m01~m11 은 4회 × 8쿼터 중 로테이션으로 약 20~26쿼터 출전)
        def record_quarters(ev, run_obj, n_quarters: int, seed: int) -> None:
            sq = sorted(run_obj.candidates[0].squads, key=lambda x: x.squad_no)
            b_ids = [sl.player_id for sl in sq[0].slots]
            w_ids = [sl.player_id for sl in sq[1].slots]
            qs = []
            for i in range(n_quarters):
                rot = lambda ids, k: [ids[(k + j) % len(ids)] for j in range(5)]
                b = 7 + (seed * 7 + i * 5) % 9
                w = 7 + (seed * 3 + i * 4) % 9
                qs.append(QuarterIn(
                    quarter_no=i + 1, black_score=b, white_score=w, duration_min=10,
                    lineups=[LineupIn(player_id=x, side=Side.BLACK) for x in rot(b_ids, i)] + [LineupIn(player_id=x, side=Side.WHITE) for x in rot(w_ids, i)],
                ))
            quarter_service.bulk_save(db, ev, manager, QuarterBulkSave(quarters=qs))
            ev.status = EventStatus.DONE

        for weeks_ago in (5, 4, 3, 2):
            ev = event_service.create_event(
                db, team, manager,
                EventCreate(title="일요 정기전", event_date=sunday - timedelta(days=7 * weeks_ago), start_time=time(10, 0), end_time=time(12, 0), venue="서초 사회체육관 2층"),
            )
            for p in players[:ATTEND]:
                event_service.respond(db, ev, p, AttendanceStatus.ATTEND, None)
            r = assignment_service.run(db, ev, manager, AssignmentRunRequest(team_count=2, constraints=ConstraintSet()))
            assignment_service.adopt(db, assignment_service._load_candidate(db, r.candidates[0].id))
            db.commit()
            record_quarters(ev, r, 8, weeks_ago)
            db.commit()

        # 3) 지난주 일요일 일정 — 게스트 초대 이력·배정 확정 이력을 남긴다
        last = event_service.create_event(
            db, team, manager,
            EventCreate(title="일요 정기전", event_date=sunday - timedelta(days=7), start_time=time(10, 0), end_time=time(12, 0), venue="서초 사회체육관 2층"),
        )
        for p in players[:ATTEND]:
            event_service.respond(db, last, p, AttendanceStatus.ATTEND, None)
        invites = [
            (4, EventGuestCreate(display_name="게스트 허웅", skill_grade=4, preferred_position=Position.SF, playable_positions=[Position.SF, Position.PF], team_lock_request=True)),
            (7, EventGuestCreate(display_name="게스트 허훈", skill_grade=3, preferred_position=Position.SG, playable_positions=[Position.SG, Position.SF], team_lock_request=True)),
            (0, EventGuestCreate(display_name="게스트 송교창", skill_grade=5, preferred_position=Position.C, playable_positions=[Position.C, Position.PF], team_lock_request=False)),
        ]
        last_guest_ids = {}
        for idx, body in invites:
            view, _ = event_service.register_guest(db, last, players[idx], users[idx], body)
            last_guest_ids[body.display_name] = view.player.id
        run = assignment_service.run(
            db, last, manager,
            AssignmentRunRequest(team_count=2, constraints=ConstraintSet(lock_groups=[[last_guest_ids["게스트 허웅"], players[4].id]])),
        )
        assignment_service.adopt(db, assignment_service._load_candidate(db, run.candidates[0].id))
        db.commit()

        # 3-a) 지난주 쿼터 기록 6개 — 확정 팀 그대로, 5명씩 로테이션. 첫 회차라 실력 지표에는 반영되지 않는다 (13.2절 1항)
        squads = sorted(run.candidates[0].squads, key=lambda s: s.squad_no)
        black_ids = [sl.player_id for sl in squads[0].slots]
        white_ids = [sl.player_id for sl in squads[1].slots]
        scores = [(12, 9), (8, 11), (10, 10), (14, 7), (9, 13), (11, 8)]
        quarters = []
        for i, (b, w) in enumerate(scores):
            rot = lambda ids, k: [ids[(k + j) % len(ids)] for j in range(5)]
            quarters.append(QuarterIn(
                quarter_no=i + 1, black_score=b, white_score=w, duration_min=10,
                lineups=[LineupIn(player_id=x, side=Side.BLACK) for x in rot(black_ids, i)] + [LineupIn(player_id=x, side=Side.WHITE) for x in rot(white_ids, i)],
            ))
        quarter_service.bulk_save(db, last, manager, QuarterBulkSave(quarters=quarters))
        last.status = EventStatus.DONE
        db.commit()

        # 3-b) 지난주 피어 투표 — 12명 중 8명 응답. 상호 지목 2쌍(0·1, 2·3), 단방향 몇 개 ('다음에 같이 뛰고 싶은 사람'만)
        pl = players
        ballots = {
            0: [VoteIn(target_player_id=pl[1].id, vote_type="PLAY_AGAIN", reason_tag="PASS"), VoteIn(target_player_id=pl[5].id, vote_type="PLAY_AGAIN")],
            1: [VoteIn(target_player_id=pl[0].id, vote_type="PLAY_AGAIN", reason_tag="TEMPO"), VoteIn(target_player_id=pl[3].id, vote_type="PLAY_AGAIN")],
            2: [VoteIn(target_player_id=pl[3].id, vote_type="PLAY_AGAIN", reason_tag="DEFENSE_HELP")],
            3: [VoteIn(target_player_id=pl[2].id, vote_type="PLAY_AGAIN", reason_tag="DEFENSE_HELP"), VoteIn(target_player_id=pl[1].id, vote_type="PLAY_AGAIN")],
            4: [VoteIn(target_player_id=last_guest_ids["게스트 허웅"], vote_type="PLAY_AGAIN", reason_tag="OTHER")],
            5: [VoteIn(target_player_id=pl[0].id, vote_type="PLAY_AGAIN"), VoteIn(target_player_id=pl[8].id, vote_type="PLAY_AGAIN", reason_tag="PASS")],
            6: [],  # 건너뛰기 (빈 제출)
            8: [VoteIn(target_player_id=pl[5].id, vote_type="PLAY_AGAIN", reason_tag="TEMPO")],
        }
        for idx, votes in ballots.items():
            peer_service.submit(db, last, pl[idx], PostGameSurveyIn(votes=votes))
        db.commit()

        # 4) 이번 주 일요일 일정
        deadline = datetime.combine(sunday - timedelta(days=1), time(22, 0)).astimezone()
        event = event_service.create_event(
            db, team, manager,
            EventCreate(title="일요 정기전", event_date=sunday, start_time=time(10, 0), end_time=time(12, 0), venue="서초 사회체육관 2층", rsvp_deadline=deadline, memo="회비 5,000원 · 게스트 환영"),
        )
        for p in players[:ATTEND]:
            event_service.respond(db, event, p, AttendanceStatus.ATTEND, None)
        for p in players[ATTEND:ATTEND + ABSENT]:
            event_service.respond(db, event, p, AttendanceStatus.ABSENT, "출장")

        # 5) 이번 주 게스트 2명 (문경은 초대). 허웅는 지난주 레코드 재사용 → 기록 누적
        inviter_user, inviter_player = users[4], players[4]
        event_service.register_guest(db, event, inviter_player, inviter_user, EventGuestCreate(display_name="게스트 허웅", skill_grade=4, preferred_position=Position.SF, playable_positions=[Position.SF, Position.PF], team_lock_request=True, existing_player_id=last_guest_ids["게스트 허웅"]))
        event_service.register_guest(db, event, inviter_player, inviter_user, EventGuestCreate(display_name="게스트 이승현", preferred_position=Position.SG, playable_positions=[Position.SG], team_lock_request=False))

        # 5-b) 게스트였던 사람이 가입한 상황 — m20 "허웅" 은 지난주 "게스트 허웅" 과 이름이 같아 홈에 "본인이 맞나요?" 카드가 뜬다
        auth_service.signup(db, SignupRequest(email="m20@demo.com", password=SecretStr(PASSWORD), name="허웅", height_cm=186))
        hw = db.scalar(select(User).where(User.email == "m20@demo.com"))
        survey_service.submit(db, hw, SurveyResponseIn(template_id=tpl.id, answers=_answers(tpl, ROSTER[5])))
        team_service.join_team(db, hw, team.team_code)

        # 6) 두 번째 팀 "수요 픽업" — 매니저·m01~m06 이 두 팀에 동시에 속한다 (메인 팀 설정 · 프로필 팀 선택 확인용)
        team2 = team_service.create_team(db, users[2], TeamCreate(name=TEAM2_NAME, description="수요일 저녁 픽업 게임", home_court="잠실 학생체육관"))
        team_service.set_approval(db, team2, admin, True)
        # 승인 대기 팀 하나 — 관리자 콘솔의 승인 액션 확인용 (m08 이 만든 "목요 픽업", 승인 전이라 일정 기능 잠김)
        team3 = team_service.create_team(db, users[8], TeamCreate(name="목요 픽업", description="승인 대기 예시"))
        for u in [users[0], users[1]] + users[3:7]:
            team_service.join_team(db, u, team2.team_code)
        for u, row in zip(users[:7], ROSTER[:7], strict=True):
            survey_service.set_self_rank(db, caller_player(db, u, team2.id), SelfRankLevel(row[2]))
        wed = sunday + timedelta(days=3)
        ev2 = event_service.create_event(db, team2, users[2], EventCreate(title="수요 픽업", event_date=wed, start_time=time(20, 0), end_time=time(22, 0), venue="잠실 학생체육관"))
        for u in users[:5]:
            event_service.respond(db, ev2, caller_player(db, u, team2.id), AttendanceStatus.ATTEND, None)
        db.commit()

        db.refresh(team)
        print("=== 데모 데이터 생성 완료 ===")
        print(f"팀: {TEAM_NAME} (코드 {team.team_code}) · 회원 20명 · 상태 {team.status}")
        print(f"지난 회차 5개: {sunday - timedelta(days=35)} ~ {sunday - timedelta(days=7)} (배정 확정 · 쿼터 8·8·8·8·6개) · 3회차부터 실력 지표 반영")
        print("지난주 일정: 게스트 3명 · 피어 투표 8/12명 응답 (m07·m09·m10·m11 미응답)")
        print(f"두 번째 팀: {TEAM2_NAME} (코드 {team2.team_code}) · 매니저 m02 이상민 · 허재·m01·m03~m06 이 두 팀 소속 → 홈에서 '기본 팀으로 설정하기' 확인")
        print(f"이번 주 일정: {sunday} 10:00 일요 정기전 · 참석 {ATTEND}명 + 게스트 2명 · 불참 {ABSENT}명 · 미응답 {len(ROSTER) - ATTEND - ABSENT}명")
        print(f"매니저 로그인: {MANAGER_EMAIL} / {PASSWORD}")
        print(f"팀원 로그인: m01@demo.com ~ m19@demo.com / {PASSWORD}")
        print("게스트 기록 본인 확인: m20@demo.com (허웅) 로 로그인하면 홈에 '게스트 허웅' 기록 확인 카드 → 내 기록이에요 / 아니에요")
        if admin:
            print(f"관리자 콘솔: http://localhost:8000/admin  (로그인 {ADMIN_EMAIL} / {PASSWORD}) · 승인 대기 팀 '{team3.name}'(m08 생성) 에서 승인 액션 확인")
        else:
            print(f"관리자 계정은 만들지 않았어요 (--no-admin). 승인 대기 팀 '{team3.name}'(m08 생성) 은 기존 관리자 콘솔에서 승인해 보세요.")
        print("데모 데이터를 지우려면: python -m scripts.remove_demo")
        print("게스트 초대 이력(불러오기 확인용):")
        print("  m04@demo.com 문경은  → 게스트 허웅(지난주+이번주), 게스트 이승현(이번주)")
        print("  m07@demo.com 김선형  → 게스트 허훈 (지난주만 → 이번 주 시트에서 불러오기 가능)")
        print(f"  {MANAGER_EMAIL} 허재 → 게스트 송교창 (지난주만 → 불러오기 가능)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
