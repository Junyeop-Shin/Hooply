"""데모 데이터 시드 — 포트폴리오 심사자가 링크 하나로 전 기능을 둘러볼 수 있는 상태를 만든다.

실행
  cd backend && uv run python -m scripts.seed_demo          # 로컬
  docker compose exec api python -m scripts.seed_demo       # 도커
  DATABASE_URL=<운영> uv run python -m scripts.seed_demo --no-admin   # 운영 DB 에 데모 팀만 (관리자 계정 생략)

만드는 것
  - 팀 "일요 코트메이트" (회원 20명 + 게스트 4명). 19명은 설문 v2 + 팀 내 자기 위치까지 마쳤고,
    한 명(m19 주희정)은 일부러 설문 전 상태로 둬서 홈의 온보딩 안내 카드를 확인할 수 있다.
  - 매니저 1명: manager@demo.com / demo1234  (이름 허재)
  - 팀원 19명: m01@demo.com ~ m19@demo.com / demo1234 · 게스트 출신 가입자 m20@demo.com (허웅)
  - 지난 10주 회차 (전부 종료): 매회 참석자 조합이 달라지고(고정 10명 + 번갈아 4명), 게스트가 섞이며,
    배정 확정 + 쿼터 7~9개 기록까지 끝나 있다. 최근 4회차에는 경기 후 투표도 들어가 있다.
      · 3회차부터 실력 지표에 반영된다 (첫 2회 게이트, 13.2절 1항)
      · 지난주 회차에는 묶기(LOCK) · 갈라놓기(SEPARATE) · 사전 배치(PIN) 세 제약이 모두 걸려 있어
        이번 주 배정 화면의 "지난 조건 불러오기" 로 세 가지를 한 번에 볼 수 있다
  - 매니저 실력 정렬 2개 버전 (F14) — 최신 버전이 활성, 이전 버전은 이력으로 남는다
  - 프로필 사진 4명 (업로드·서빙 경로 확인용 자리 이미지, 매니저는 제외)
  - 앞으로의 일정 3건
      · 이번 주 일요일 — 참석 응답 완료, **배정은 일부러 실행하지 않음** (심사자가 직접 돌려 보는 화면)
      · 다음 주 일요일 — 참석 응답 완료, 역시 배정 전 (심사자가 두 번 해 볼 수 있게)
      · 2주 뒤 일요일 — 응답 수집 중 (미응답 다수 → RSVP 확인용)
      · 3주 뒤 일정 1건은 취소됨 (취소 상태 표시 확인용)
  - 두 번째 팀 "수요 픽업" (기본 팀 설정 확인용) · 승인 대기 팀 "목요 픽업"
  이미 팀이 있으면 아무것도 만들지 않고 계정 정보만 출력한다 (멱등).

서비스 함수를 그대로 호출하므로 API 로 만든 것과 같은 상태가 된다.
"""

from __future__ import annotations

import base64
import random
import struct
import zlib
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
from app.schemas.assignment import AssignmentRunRequest, ConstraintSet, PinConstraint
from app.schemas.auth import SignupRequest
from app.schemas.event import EventCreate, EventGuestCreate
from app.schemas.game import LineupIn, QuarterBulkSave, QuarterIn
from app.schemas.peer import PostGameSurveyIn, VoteIn
from app.schemas.survey import SurveyAnswerIn, SurveyResponseIn
from app.schemas.team import TeamCreate
from app.services import (
    assignment_service,
    auth_service,
    avatar_service,
    event_service,
    peer_service,
    quarter_service,
    ranking_service,
    survey_service,
    team_service,
)
from app.services.guest_service import caller_player

TEAM2_NAME = "수요 픽업"
TEAM3_NAME = "목요 픽업"
ADMIN_EMAIL = "admin@demo.com"
TEAM_NAME = "일요 코트메이트"
PASSWORD = "demo1234"
MANAGER_EMAIL = "manager@demo.com"

# (이름, 키, 자기 위치, 선호 포지션 순서, 1번 D3A, 5번 D3B, 경기 수준, 슛 거리, 볼 운반, 수비1, 수비2, 성향, 체력, 공격 옵션)
# 포지션이 골고루 섞이고 실력이 갈리도록 구성.
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
    # ── 여기까지 10명이 출석률 높은 고정 멤버 ──
    ("하승진", 195, "BOT30", ["C"], "CANNOT", "CAN_NO_PREFER", "STREET", "LAYUP", "NO_DRIVE", "CHASE", "HELP_NO_RECOVER", "OFFBALL", "Q1", ["PUTBACK", "POST_UP"]),
    ("조성원", 177, "BOT10", ["SF", "SG"], "CANNOT", "CANNOT", "PE", "FT_LINE", "NO_DRIVE", "UNAWARE", "OWN_ONLY", "OFFBALL", "Q2", ["OFFBALL_CUT"]),
    ("추승균", 181, "TOP30", ["SG", "SF"], "CAN_NO_PREFER", "CANNOT", "AMATEUR", "THREE", "HALF_COURT", "SWITCH", "HELP_RECOVER", "MOSTLY_ONBALL", "FULL", ["PULLUP", "DRIVE_FINISH", "CATCH_SHOOT"]),
    ("우지원", 186, "MID", ["PF"], "CANNOT", "CAN_NO_PREFER", "CLUB", "FLOATER", "LIGHT_PRESS", "SWITCH", "HELP_RECOVER", "OFFBALL", "Q3_4", ["POST_UP", "PUTBACK"]),
    ("전희철", 175, "BOT30", ["PG"], "CAN_NO_PREFER", "CANNOT", "STREET", "FT_LINE", "LIGHT_PRESS", "CHASE", "HELP_NO_RECOVER", "MOSTLY_ONBALL", "Q2", ["DRIVE_FINISH"]),
    ("강동희", 179, "MID", ["SF", "SG"], "CANNOT", "CANNOT", "CLUB", "THREE", "LIGHT_PRESS", "CHASE", "HELP_RECOVER", "MOSTLY_OFFBALL", "Q3_4", ["CATCH_SHOOT", "OFFBALL_CUT"]),
    ("김유택", 184, "MID", ["PF", "SF"], "CANNOT", "CAN_NO_PREFER", "CLUB", "FT_LINE", "LIGHT_PRESS", "SWITCH", "HELP_NO_RECOVER", "OFFBALL", "Q3_4", ["PUTBACK", "OFFBALL_CUT"]),
    ("한기범", 171, "BOT10", ["PG", "SG"], "CAN_NO_PREFER", "CANNOT", "PE", "LAYUP", "LIGHT_PRESS", "UNAWARE", "OWN_ONLY", "MOSTLY_ONBALL", "Q1", ["DRIVE_FINISH"]),
    ("이충희", 189, "TOP30", ["C", "PF"], "CANNOT", "CAN_PREFER", "AMATEUR", "FLOATER", "LIGHT_PRESS", "READ", "HELP_RECOVER", "OFFBALL", "FULL", ["POST_UP", "PNR_ROLL_POP", "PUTBACK"]),
    ("주희정", 180, "MID", ["SG", "SF", "PG"], "CAN_NO_PREFER", "CANNOT", "CLUB", "THREE", "HALF_COURT", "SWITCH", "HELP_RECOVER", "MOSTLY_ONBALL", "Q3_4", ["CATCH_SHOOT", "PULLUP", "PNR_HANDLER"]),
]

CORE = list(range(10))          # 매회 나오는 고정 멤버
ROTATING = list(range(10, 19))  # 번갈아 나오는 멤버 (매회 4명)
NO_SURVEY_IDX = 19              # 설문 전 상태로 남겨 둘 사람 (m19 주희정) — 홈 온보딩 카드 확인용
PAST_WEEKS = 10                 # 지난 회차 수 (주 1회)
VOTE_WEEKS = 4                  # 최근 몇 회차에 경기 후 투표를 넣을지
AVATAR_IDX = [1, 2, 4, 7]       # 프로필 사진을 넣어 둘 사람. 매니저(0)는 비워 둔다 — e2e/avatar.spec 이 사진 없는 상태에서 시작한다

# 서로 지목하는 조합 — 여러 회차에 걸쳐 반복되어야 "선호 조합" 신호가 쌓인다 (9.4절)
MUTUAL_PAIRS = [(0, 1), (2, 3), (5, 8)]

# 시뮬레이션용 "진짜 실력" — 쿼터당 득실 기여(점). 쿼터 점수를 여기서 만들어 내므로
# 잔차 기반 실력 지표(9.2절)가 설문·매니저 정렬과 대체로 맞아떨어진다. 점수를 라인업과
# 무관한 난수로 만들면 강한 선수일수록 기대 마진이 커서 잔차가 음수로 쌓이고, 화면의
# 실력 순위가 설문과 정반대로 뒤집힌다 (9.1절 역선택과 같은 모양의 인공물).
TRUE_BY_RANK = {"TOP10": 2.6, "TOP30": 1.3, "MID": 0.0, "BOT30": -1.3, "BOT10": -2.6}
TRUE_BY_GRADE = {5: 2.2, 4: 1.1, 3: 0.0, 2: -1.1, 1: -2.2}
QUARTER_NOISE_SD = 5.0  # 쿼터 마진 노이즈 (설계서 9.3절 모의 조건과 같은 크기)
SIM_SEED = 20260917

# 게스트 4명. inviter 는 ROSTER 인덱스. 이름은 실제 사용자가 입력하듯 접두어 없이 적는다 —
# 매니저의 병합 제안(merge_candidates)은 이름 완전 일치로 찾으므로 "게스트 허웅" 이면 회원 "허웅" 과 짝지어지지 않는다
GUEST_SPECS: dict[str, dict] = {
    "허웅": {"inviter": 4, "skill_grade": 4, "height_cm": 186, "preferred": Position.SF, "playable": [Position.SF, Position.PF], "lock": True},
    "허훈": {"inviter": 7, "skill_grade": 3, "height_cm": 180, "preferred": Position.SG, "playable": [Position.SG, Position.SF], "lock": True},
    "송교창": {"inviter": 0, "skill_grade": 5, "height_cm": 195, "preferred": Position.C, "playable": [Position.C, Position.PF], "lock": False},
    "이승현": {"inviter": 4, "skill_grade": None, "height_cm": None, "preferred": Position.SG, "playable": [Position.SG], "lock": False},
}
# 회차별 게스트 (weeks_ago → 이름들). 같은 이름이 다시 나오면 기존 레코드를 재사용해 기록이 누적된다 (FR-12)
GUESTS_BY_WEEK: dict[int, list[str]] = {
    7: ["허훈"],
    5: ["송교창"],
    4: ["허웅"],
    2: ["허웅", "허훈"],
    1: ["허웅", "허훈", "송교창"],
}


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


def attendees_of(weeks_ago: int) -> list[int]:
    """그 회차 참석자의 ROSTER 인덱스 — 고정 10명 + 번갈아 4명. 회차마다 조합이 달라야 실력 추정이 된다 (9.3절)."""
    rot = [ROTATING[(weeks_ago * 4 + k) % len(ROTATING)] for k in range(4)]
    return CORE + sorted(rot)


def _avatar_data_url(seed: int) -> str:
    """96×96 그라데이션 PNG 를 데이터 URL 로. 프로필 사진 업로드·서빙 경로를 실제로 태우기 위한 자리 이미지."""
    palette = [(0x1F, 0x3A, 0x5F), (0xE0, 0x6C, 0x2A), (0x2E, 0x7D, 0x5E), (0x7A, 0x3E, 0x8F), (0xB3, 0x3C, 0x46)]
    r, g, b = palette[seed % len(palette)]
    size, raw = 96, bytearray()
    for y in range(size):
        raw.append(0)  # 필터 타입 0
        for x in range(size):
            t = 0.55 + 0.5 * (x + y) / (2 * size - 2)
            raw += bytes((min(255, int(r * t)), min(255, int(g * t)), min(255, int(b * t))))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


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

        # 1) 계정 + 설문. NO_SURVEY_IDX 한 명만 설문 전 상태로 남긴다
        users: list[User] = []
        for i, row in enumerate(ROSTER):
            email = MANAGER_EMAIL if i == 0 else f"m{i:02d}@demo.com"
            auth_service.signup(db, SignupRequest(email=email, password=SecretStr(PASSWORD), name=row[0], height_cm=row[1]))
            user = db.scalar(select(User).where(User.email == email))
            if i != NO_SURVEY_IDX:
                survey_service.submit(db, user, SurveyResponseIn(template_id=tpl.id, answers=_answers(tpl, row)))
            users.append(user)

        # 1-b) 관리자 계정 — SQLAdmin(/admin)·관리자 API 확인용. 팀에는 속하지 않는다 (--no-admin 이면 건너뜀)
        admin = None
        if not no_admin:
            auth_service.signup(db, SignupRequest(email=ADMIN_EMAIL, password=SecretStr(PASSWORD), name="관리자"))
            admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
            admin.global_role = GlobalRole.ADMIN
            db.commit()

        # 1-c) 프로필 사진 몇 명 — 팀원 목록·배정 화면에 사진이 섞여 보이게
        for i in AVATAR_IDX:
            avatar_service.set_avatar(db, users[i], _avatar_data_url(i))

        # 2) 팀 + 가입 + 자기 위치
        manager = users[0]
        team = team_service.create_team(db, manager, TeamCreate(name=TEAM_NAME, description="매주 일요일 오전, 게스트 환영", home_court="서초 사회체육관"))
        team_service.set_approval(db, team, admin, True)  # 관리자 승인 (콘솔에서 하는 것과 같은 처리)
        for u in users[1:]:
            team_service.join_team(db, u, team.team_code)
        for i, (u, row) in enumerate(zip(users, ROSTER, strict=True)):
            if i == NO_SURVEY_IDX:
                continue  # 설문 전이므로 자기 위치도 비워 둔다
            survey_service.set_self_rank(db, caller_player(db, u, team.id), SelfRankLevel(row[2]))

        players = [caller_player(db, u, team.id) for u in users]
        sunday = next_sunday()
        guest_ids: dict[str, int] = {}  # 이름 → players.id (재방문 시 재사용)

        rng = random.Random(SIM_SEED)  # 점수 노이즈 난수열 고정. 배정 결과가 실행 시각·id 에 따라 조금씩 달라서 지표 수치는 실행마다 약간 다르다
        # 숨은 참값: 회원은 자기 위치 구간에서, 같은 구간 안에서도 조금씩 다르게
        true_skill: dict[int, float] = {
            players[i].id: TRUE_BY_RANK[row[2]] + ((i % 5) - 2) * 0.18
            for i, row in enumerate(ROSTER)
        }

        def invite_guests(ev, names: list[str]) -> None:
            for name in names:
                spec = GUEST_SPECS[name]
                idx = spec["inviter"]
                body = EventGuestCreate(
                    display_name=name, skill_grade=spec["skill_grade"], height_cm=spec["height_cm"],
                    preferred_position=spec["preferred"], playable_positions=spec["playable"],
                    team_lock_request=spec["lock"], existing_player_id=guest_ids.get(name),
                )
                view, _ = event_service.register_guest(db, ev, players[idx], users[idx], body)
                guest_ids[name] = view.player.id
                true_skill.setdefault(view.player.id, TRUE_BY_GRADE.get(spec["skill_grade"], 0.0))

        def constraints_of(weeks_ago: int) -> ConstraintSet:
            """회차별 배정 제약. 지난주에는 세 종류를 모두 걸어 둔다 — 이번 주 '지난 조건 불러오기' 로 확인한다."""
            if weeks_ago == 1:
                return ConstraintSet(
                    lock_groups=[[guest_ids["허웅"], players[4].id]],      # 초대자와 같은 팀 요청
                    separate_groups=[[players[1].id, players[2].id]],             # 상위 둘은 갈라놓기
                    pins=[PinConstraint(player_id=players[0].id, squad_no=1)],    # 매니저는 블랙 고정
                )
            if weeks_ago == 3:
                return ConstraintSet(lock_groups=[[players[6].id, players[9].id]])
            return ConstraintSet()

        def record_quarters(ev, cand, n_quarters: int) -> None:
            """확정된 두 팀 그대로 5명씩 로테이션. 점수는 그 쿼터에 실제로 뛴 10명의 진짜 실력에서 만든다.

            마진 = (블랙 5명 실력 합) − (화이트 5명 실력 합) + 노이즈. 이렇게 해야 잔차 기반 실력
            지표가 의미 있는 값으로 수렴한다 (9.2절). 점수를 라인업과 무관하게 찍으면 지표가
            설문·정렬과 반대로 뒤집힌 채 쌓인다.
            """
            sq = sorted(cand.squads, key=lambda x: x.squad_no)
            b_ids = [sl.player_id for sl in sq[0].slots]
            w_ids = [sl.player_id for sl in sq[1].slots]
            qs = []
            for i in range(n_quarters):
                bl = [b_ids[(i + j) % len(b_ids)] for j in range(5)]
                wl = [w_ids[(i + j) % len(w_ids)] for j in range(5)]
                diff = sum(true_skill.get(x, 0.0) for x in bl) - sum(true_skill.get(x, 0.0) for x in wl)
                m = max(-15, min(15, round(diff + rng.gauss(0, QUARTER_NOISE_SD))))
                base = rng.randint(8, 12)
                qs.append(QuarterIn(
                    quarter_no=i + 1, black_score=base + max(m, 0), white_score=base + max(-m, 0), duration_min=10,
                    lineups=(
                        [LineupIn(player_id=x, side=Side.BLACK) for x in bl]
                        + [LineupIn(player_id=x, side=Side.WHITE) for x in wl]
                    ),
                ))
            quarter_service.bulk_save(db, ev, manager, QuarterBulkSave(quarters=qs))
            ev.status = EventStatus.DONE

        def cast_votes(ev, cand, attend_idx: list[int], weeks_ago: int) -> None:
            """경기 후 투표. 상호 지목 조합은 같은 팀일 때마다 서로를 고르고, 나머지는 회차마다 한 명씩 흩어진다.

            같은 팀/상대 팀에서 각각 최대 2명까지만 고를 수 있다 (peer_service.submit).
            일부러 몇 명은 응답하지 않고 남겨 둔다 — 매니저의 독려 카드와 심사자가 직접 투표할 자리.
            """
            squads = sorted(cand.squads, key=lambda s: s.squad_no)
            side_of = {sl.player_id: n for n, sq in enumerate(squads) for sl in sq.slots}
            pid_of = {i: players[i].id for i in attend_idx}
            fav = {a: b for a, b in MUTUAL_PAIRS} | {b: a for a, b in MUTUAL_PAIRS}
            reasons = ["PASS", "TEMPO", "DEFENSE_HELP", "OTHER"]
            skip = {(weeks_ago * 3 + k) % len(attend_idx) for k in range(3)}  # 회차마다 3명은 미응답
            for n, i in enumerate(attend_idx):
                if n in skip or i == NO_SURVEY_IDX:
                    continue
                me = pid_of[i]
                picked, per_side = [], {0: 0, 1: 0}
                order = [fav.get(i)] + [j for j in attend_idx if j != i]
                for j in order:
                    if j is None or j not in pid_of or j == i:
                        continue
                    target = pid_of[j]
                    if target in picked or me not in side_of or target not in side_of:
                        continue
                    same = 0 if side_of[target] == side_of[me] else 1
                    if per_side[same] >= 1:  # 같은 팀 1명 + 상대 팀 1명씩만 (최대 2명 중 1명)
                        continue
                    per_side[same] += 1
                    picked.append(target)
                    if len(picked) == 2:
                        break
                votes = [
                    VoteIn(target_player_id=t, vote_type="PLAY_AGAIN", reason_tag=reasons[(i + k) % len(reasons)])
                    for k, t in enumerate(picked)
                ]
                peer_service.submit(db, ev, players[i], PostGameSurveyIn(votes=votes))

        # 3) 지난 10주 회차 — 참석 조합·게스트·쿼터 수가 매회 다르고, 배정 확정까지 끝나 있다
        for weeks_ago in range(PAST_WEEKS, 0, -1):
            attend_idx = attendees_of(weeks_ago)
            ev = event_service.create_event(
                db, team, manager,
                EventCreate(
                    title="일요 정기전", event_date=sunday - timedelta(days=7 * weeks_ago),
                    start_time=time(10, 0), end_time=time(12, 0), venue="서초 사회체육관 2층",
                ),
            )
            for i in attend_idx:
                event_service.respond(db, ev, players[i], AttendanceStatus.ATTEND, None)
            invite_guests(ev, GUESTS_BY_WEEK.get(weeks_ago, []))
            r = assignment_service.run(db, ev, manager, AssignmentRunRequest(team_count=2, constraints=constraints_of(weeks_ago)))
            # 회차마다 채택하는 전략을 바꿔 둔다 (실력 우선 / 친화도 우선 / 종합)
            cand = assignment_service._load_candidate(db, r.candidates[weeks_ago % len(r.candidates)].id)
            assignment_service.adopt(db, cand)
            db.commit()
            adopted = assignment_service.adopted_candidate(db, ev)
            record_quarters(ev, adopted, 7 + weeks_ago % 3)
            db.commit()
            if weeks_ago <= VOTE_WEEKS:
                cast_votes(ev, adopted, attend_idx, weeks_ago)
                db.commit()

        # 4) 매니저 실력 정렬 2개 버전 (F14) — 최신이 활성, 이전 것은 이력으로 남는다
        ranked = [i for i in range(len(ROSTER)) if i != NO_SURVEY_IDX]
        order_v1 = [players[i].id for i in ranked]
        swapped = ranked[:]
        swapped[3], swapped[5] = swapped[5], swapped[3]  # 한 달 뒤 매니저가 두 사람 순서를 바꿔 다시 저장
        ranking_service.create(db, team, manager, order_v1)
        ranking_service.create(db, team, manager, [players[i].id for i in swapped])

        # 5) 앞으로의 일정 — 이번 주·다음 주는 응답 완료(배정 전), 2주 뒤는 응답 수집 중
        def upcoming(weeks_ahead: int, *, responded: bool, guests: list[str]) -> None:
            day = sunday + timedelta(days=7 * weeks_ahead)
            deadline = datetime.combine(day - timedelta(days=1), time(22, 0)).astimezone()
            ev = event_service.create_event(
                db, team, manager,
                EventCreate(
                    title="일요 정기전", event_date=day, start_time=time(10, 0), end_time=time(12, 0),
                    venue="서초 사회체육관 2층", rsvp_deadline=deadline, memo="회비 5,000원 · 게스트 환영",
                ),
            )
            attend_idx = attendees_of(weeks_ahead + PAST_WEEKS)
            if responded:
                for i in attend_idx:
                    event_service.respond(db, ev, players[i], AttendanceStatus.ATTEND, None)
                for i in [j for j in range(len(ROSTER)) if j not in attend_idx][:3]:
                    event_service.respond(db, ev, players[i], AttendanceStatus.ABSENT, "출장")
            else:
                for i in attend_idx[:5]:  # 아직 다섯 명만 응답 — 나머지는 미응답
                    event_service.respond(db, ev, players[i], AttendanceStatus.ATTEND, None)
            invite_guests(ev, guests)

        upcoming(0, responded=True, guests=["허웅", "이승현"])
        upcoming(1, responded=True, guests=["허훈"])
        upcoming(2, responded=False, guests=[])

        # 5-b) 취소된 일정 1건 — 목록의 '취소됨' 표시 확인용
        canceled = event_service.create_event(
            db, team, manager,
            EventCreate(title="우천 취소된 번개", event_date=sunday + timedelta(days=24), start_time=time(19, 0), end_time=time(21, 0), venue="양재 시민의숲 코트"),
        )
        event_service.cancel_event(db, canceled)

        # 6) 게스트였던 사람이 가입한 상황 — m20 "허웅" 은 "허웅" 과 이름이 같아
        #    본인 홈에 "본인이 맞나요?" 카드가, 매니저의 팀원 관리에 "기록 이어받기 제안" 이 뜬다
        auth_service.signup(db, SignupRequest(email="m20@demo.com", password=SecretStr(PASSWORD), name="허웅", height_cm=186))
        hw = db.scalar(select(User).where(User.email == "m20@demo.com"))
        survey_service.submit(db, hw, SurveyResponseIn(template_id=tpl.id, answers=_answers(tpl, ROSTER[5])))
        team_service.join_team(db, hw, team.team_code)

        # 7) 두 번째 팀 "수요 픽업" — 매니저·m01~m06 이 두 팀에 동시에 속한다 (기본 팀 설정 · 프로필 팀 선택 확인용)
        team2 = team_service.create_team(db, users[2], TeamCreate(name=TEAM2_NAME, description="수요일 저녁 픽업 게임", home_court="잠실 학생체육관"))
        team_service.set_approval(db, team2, admin, True)
        # 승인 대기 팀 하나 — 승인 전이라 일정 기능이 잠긴 상태를 보여 준다 (m08 이 만든 팀)
        team_service.create_team(db, users[8], TeamCreate(name=TEAM3_NAME, description="승인 대기 예시"))
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
        print(f"팀: {TEAM_NAME} (코드 {team.team_code}) · 회원 {team_service.member_count(db, team.id)}명 · 상태 {team.status}")
        print(f"지난 회차 {PAST_WEEKS}개: {sunday - timedelta(days=7 * PAST_WEEKS)} ~ {sunday - timedelta(days=7)} · 전부 배정 확정 + 쿼터 기록 · 3회차부터 실력 지표 반영")
        print(f"최근 {VOTE_WEEKS}회차에는 경기 후 투표가 들어가 있어요 (회차마다 3명은 미응답 — 직접 투표해 볼 수 있어요)")
        print("지난주 회차 제약: 묶기(게스트 허웅+초대자 문경은) · 갈라놓기(서장훈/이상민) · 사전 배치(허재→블랙) → 이번 주 배정 화면의 '지난 조건 불러오기'")
        print("매니저 실력 정렬: 2개 버전 저장됨 (최신이 활성)")
        print(f"앞으로의 일정: {sunday} / {sunday + timedelta(days=7)} 는 응답 완료 · **배정 전** (직접 실행해 보세요) · {sunday + timedelta(days=14)} 는 응답 수집 중 · {canceled.event_date} 는 취소됨")
        print(f"두 번째 팀: {TEAM2_NAME} (코드 {team2.team_code}) · 매니저 m02 이상민 · 허재·m01·m03~m06 이 두 팀 소속 → 홈에서 '기본 팀으로 설정하기'")
        print(f"승인 대기 팀: {TEAM3_NAME} (m08 오세근 생성) — 승인 전이라 일정 기능이 잠겨 있어요")
        print(f"매니저 로그인: {MANAGER_EMAIL} / {PASSWORD}")
        print(f"팀원 로그인: m01@demo.com ~ m19@demo.com / {PASSWORD}  (m19 주희정은 설문 전 상태)")
        print("게스트 기록 본인 확인: m20@demo.com (허웅) 로그인 → 홈의 '본인이 맞나요?' 카드 · 매니저 팀원 관리에는 '기록 이어받기 제안'")
        if admin:
            print(f"관리자 콘솔: /admin  (로그인 {ADMIN_EMAIL} / {PASSWORD})")
        else:
            print("관리자 계정은 만들지 않았어요 (--no-admin).")
        print("데모 데이터를 지우려면: python -m scripts.remove_demo")
    finally:
        db.close()


if __name__ == "__main__":
    main()
