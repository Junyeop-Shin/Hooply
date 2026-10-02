"""하드닝 묶음 (0025 · 0026): 동시성 409 · 요청 제한 · 토큰 세대 · 운영 키 · 요청 크기 · 관리자 보정 오프셋 ·
배정 잠금 · 쿼터 점수 상한 · 탈퇴 비식별화 · 이메일 소문자 · 활성 정렬 하나 · 팀 전술 FK · 쿼터 기록의 팀 번호."""

import threading
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core import errors, ratelimit
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models import ManagerRanking, Player, TacticComment, TacticStar, User
from tests.test_quarters import BOT5, TOP5, _event, _lineups
from tests.test_ranking_assignment import (  # noqa: F401 — 픽스처 재사용
    ROSTER,
    _event_with_attendance,
    club,
)

API = "/api/v1"


@pytest.fixture(autouse=True)
def _limits_off():
    ratelimit.reset()
    yield
    get_settings().rate_limit_enabled = False
    ratelimit.reset()


# ---------------------------------------------------------------------------
# C1 동시성
# ---------------------------------------------------------------------------


class _Orig(Exception):
    def __init__(self, sqlstate: str):
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


# 검증: DB 유니크 위반 · 교착은 500 이 아니라 409 CONFLICT, CHECK 위반은 400
def test_db_errors_map_to_409_and_400():
    app = FastAPI()
    errors.install_error_handlers(app)

    @app.get("/{state}")
    def boom(state: str):
        raise IntegrityError("INSERT …", {}, _Orig(state))

    c = TestClient(app, raise_server_exceptions=False)
    for state in ("23505", "23503", "40P01"):
        r = c.get(f"/{state}")
        assert r.status_code == 409 and r.json()["code"] == "CONFLICT"
    r = c.get("/23514")
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    assert c.get("/XX000").status_code == 500


# 검증: 같은 refresh 토큰으로 동시에 두 번 갱신하면 하나만 성공하고 나머지는 401 (500 아님)
def test_concurrent_refresh_one_wins(client, signup):
    signup("race@example.com")
    pair = client.post(f"{API}/auth/login", json={"email": "race@example.com", "password": "password123"}).json()
    codes: list[int] = []
    barrier = threading.Barrier(4)

    def go():
        barrier.wait()
        codes.append(client.post(f"{API}/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code)

    threads = [threading.Thread(target=go) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 401, 401, 401]


# 검증: 경기 후 투표를 동시에 제출해도 선호 조합(chemistry_scores) INSERT 가 겹쳐 500 이 나지 않는다
def test_concurrent_votes_no_500(client, club):
    m = club["manager"]
    eid = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": "2026-09-01"}, headers=m).json()["id"]
    for h in club["members"]:
        client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h)
    names = [n for n, *_ in ROSTER[:6]]
    codes: list[int] = []
    barrier = threading.Barrier(6)

    def vote(i):
        partner = club["pid"][names[i ^ 1]]  # 0↔1, 2↔3, 4↔5 — 서로 지목해 같은 페어 행을 두 요청이 동시에 만든다
        barrier.wait()
        r = client.post(f"{API}/events/{eid}/post-game-survey", json={"votes": [{"target_player_id": partner, "vote_type": "PLAY_AGAIN"}]}, headers=club["members"][i])
        codes.append(r.status_code)

    threads = [threading.Thread(target=vote, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(c in (200, 201) for c in codes), codes
    stats = client.get(f"{API}/players/{club['pid'][names[0]]}/stats", headers=m).json()
    assert stats["play_again_mutual"] == 1  # 상호 지목이 한 페어로 집계됐다


# 검증: 같은 게스트를 같은 이름으로 다시 초대하면 초대 이력 한 줄의 횟수만 오른다 (ON CONFLICT 업서트), 등급은 주지 않으면 유지
def test_guest_preset_upsert(client, club):
    eid, _ = _event_with_attendance(client, club, guests=0)
    h = club["members"][1]
    r = client.post(f"{API}/events/{eid}/guests", json={"display_name": "단골", "skill_grade": 4, "height_cm": 180}, headers=h)
    assert r.status_code == 201, r.text
    gid = r.json()["player"]["id"]
    eid2 = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": "2026-09-20"}, headers=club["manager"]).json()["id"]
    assert client.post(f"{API}/events/{eid2}/guests", json={"display_name": "단골", "existing_player_id": gid}, headers=h).status_code == 201
    presets = client.get(f"{API}/events/{eid2}/guests/presets", headers=h).json()["items"]
    mine = [p for p in presets if p["display_name"] == "단골"]
    assert len(mine) == 1 and mine[0]["use_count"] == 2 and mine[0]["skill_grade"] == 4 and mine[0]["height_cm"] == 180


# ---------------------------------------------------------------------------
# C2 요청 제한
# ---------------------------------------------------------------------------


class _Req:
    def __init__(self, headers: dict[str, str], host: str = "10.0.0.1"):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


# 검증: Cloudflare 가 넣는 CF-Connecting-IP 를 믿고, 꾸밀 수 있는 X-Forwarded-For 의 첫 값은 믿지 않는다
def test_client_ip_prefers_cloudflare_header():
    assert ratelimit.client_ip(_Req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9"})) == "1.2.3.4"
    assert ratelimit.client_ip(_Req({"true-client-ip": "5.6.7.8"})) == "5.6.7.8"
    assert ratelimit.client_ip(_Req({"x-forwarded-for": "9.9.9.9, 1.1.1.1"})) == "10.0.0.1"


# 검증: 창이 지난 키는 훑어 지우고, 키가 너무 많으면 오래된 것부터 버린다 (메모리가 계속 늘지 않게)
def test_ratelimit_store_is_bounded(monkeypatch):
    get_settings().rate_limit_enabled = True
    now = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(ratelimit, "_last_sweep", now[0])
    for i in range(50):
        ratelimit.check(f"k{i}", 5, 60)
    assert len(ratelimit._hits) == 50
    now[0] += 61 + ratelimit.SWEEP_INTERVAL
    ratelimit.check("fresh", 5, 60)  # 스윕이 돌면서 창이 지난 50개를 지운다
    assert set(ratelimit._hits) == {"fresh"}
    monkeypatch.setattr(ratelimit, "MAX_KEYS", 10)
    for i in range(30):
        now[0] += 0.001
        ratelimit.check(f"x{i}", 5, 60)
    assert len(ratelimit._hits) <= 11


# 검증: 비밀번호 찾기 · 가입도 이메일 기준으로 센다 — IP 를 바꿔도 같은 이메일은 막힌다
def test_forgot_and_signup_limited_by_email(client):
    get_settings().rate_limit_enabled = True
    codes = [
        client.post(f"{API}/auth/password/forgot", json={"email": "Target@Example.com"}, headers={"cf-connecting-ip": f"7.7.7.{i}"}).status_code
        for i in range(ratelimit.PASSWORD.limit + 1)
    ]
    assert codes[:-1] == [202] * ratelimit.PASSWORD.limit and codes[-1] == 429
    body = {"email": "dup@example.com", "password": "password123", "name": "x"}
    codes = [client.post(f"{API}/auth/signup", json=body, headers={"cf-connecting-ip": f"8.8.8.{i}"}).status_code for i in range(ratelimit.SIGNUP.limit + 1)]
    assert codes[0] == 201 and codes[-1] == 429


# ---------------------------------------------------------------------------
# C6 토큰 세대 · C11 시간 차
# ---------------------------------------------------------------------------


# 검증: 비밀번호 재설정도 세대를 올려 예전 토큰을 모두 막는다. ver 클레임이 없는 예전 토큰은 0 세대로 통한다
def test_reset_password_revokes_sessions(client, signup, monkeypatch):
    from app.core.security import create_access_token
    from app.services import mail_service

    h = signup("reset@example.com")
    sent: list[str] = []
    monkeypatch.setattr(mail_service, "send_password_reset", lambda to, link: sent.append(link) or True)
    assert client.post(f"{API}/auth/password/forgot", json={"email": "reset@example.com"}).status_code == 202
    assert len(sent) == 1  # 응답 뒤 백그라운드에서 보냈다
    uid = client.get(f"{API}/me", headers=h).json()["id"]
    from jose import jwt

    s = get_settings()
    legacy = jwt.encode({"sub": str(uid), "type": "access", "exp": datetime.now(UTC).timestamp() + 600}, s.jwt_secret_key, algorithm=s.jwt_algorithm)
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200
    token = sent[0].split("token=")[1]
    assert client.post(f"{API}/auth/password/reset", json={"token": token, "new_password": "brandnew123"}).status_code == 200
    assert client.get(f"{API}/me", headers=h).status_code == 401
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {create_access_token(uid, 1)}"}).status_code == 200


# 검증: 없는 계정으로 로그인해도 bcrypt 검증을 한 번 돌린다 (응답 시간으로 가입 여부가 드러나지 않게)
def test_login_unknown_user_still_verifies(client, monkeypatch):
    from app.services import auth_service

    calls: list[str] = []
    real = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: calls.append(h) or real(p, h))
    r = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "password123"})
    assert r.status_code == 401 and len(calls) == 1


# ---------------------------------------------------------------------------
# C7 운영 키
# ---------------------------------------------------------------------------


# 검증: 운영처럼 보이는 환경(docs 닫힘 · HTTPS 쿠키 · APP_ENV · RENDER)에서 기본 JWT 키면 설정 단계에서 멈춘다
def test_default_secret_refused_in_production(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    assert Settings(_env_file=None, jwt_secret_key="change-me").jwt_secret_key == "change-me"  # 로컬은 그대로
    for kw in ({"docs_enabled": False}, {"admin_cookie_secure": True}, {"app_env": "production"}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, jwt_secret_key="change-me", **kw)
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(ValueError):
        Settings(_env_file=None, jwt_secret_key="change-me")
    assert Settings(_env_file=None, jwt_secret_key="ci-only-secret", docs_enabled=False).docs_enabled is False


# ---------------------------------------------------------------------------
# C10 요청 크기 · 사진 주소
# ---------------------------------------------------------------------------


# 검증: 전략은 3개까지(중복은 하나로), 제약 그룹 수 · 크기 상한, 메모 · 사진 데이터 길이, 프로필 사진 주소는 카카오 CDN · 내 사진만
def test_request_size_limits(client, signup):
    from app.schemas.assignment import AssignmentRunRequest

    assert AssignmentRunRequest(strategies=["SKILL", "SKILL", "BALANCED"]).strategies == ["SKILL", "BALANCED"]
    with pytest.raises(ValueError):
        AssignmentRunRequest(strategies=["SKILL"] * 4)
    with pytest.raises(ValueError):
        AssignmentRunRequest(constraints={"lock_groups": [[1, 2]] * 31})
    with pytest.raises(ValueError):
        AssignmentRunRequest(constraints={"separate_groups": [list(range(31))]})
    h = signup("size@example.com")
    assert client.post(f"{API}/me/avatar", json={"data_url": "data:image/jpeg;base64," + "A" * 700_000}, headers=h).status_code == 400
    assert client.patch(f"{API}/me", json={"profile_image_url": "https://evil.example.com/x.png"}, headers=h).status_code == 400
    assert client.patch(f"{API}/me", json={"profile_image_url": "https://k.kakaocdn.net.evil.com/x.png"}, headers=h).status_code == 400
    r = client.patch(f"{API}/me", json={"profile_image_url": "http://k.kakaocdn.net/dn/abc/img.jpg"}, headers=h)
    assert r.status_code == 200 and r.json()["profile_image_url"] == "http://k.kakaocdn.net/dn/abc/img.jpg"
    assert client.patch(f"{API}/me", json={"profile_image_url": "/api/v1/users/1/avatar?v=abc_DEF-1"}, headers=h).status_code == 200
    assert client.post(f"{API}/teams", json={"name": "t", "description": "x" * 501}, headers=h).status_code == 400


# ---------------------------------------------------------------------------
# C5 관리자 보정
# ---------------------------------------------------------------------------


def _make_admin(client, signup):
    h = signup("admin@hooply.com", name="관리자")
    with SessionLocal() as db:
        db.execute(text("UPDATE users SET global_role = 'ADMIN' WHERE email = 'admin@hooply.com'"))
        db.commit()
    return h


def _skill(client, club, name):
    cards = client.get(f"{API}/teams/{club['team_id']}/players", headers=club["manager"]).json()["items"]
    c = next(c for c in cards if c["display_name"] == name)
    return float(c["skill_overall"]), float(c["prior_overall"])


# 검증: 보정 → 정렬(사전값 재계산) → 쿼터 저장을 거쳐도 보정이 지워지거나 두 번 더해지지 않는다
def test_admin_adjust_survives_recompute(client, signup, club):
    admin = _make_admin(client, signup)
    name = ROSTER[11][0]
    pid = club["pid"][name]
    r = client.patch(f"{API}/admin/players/{pid}/rating", json={"skill_overall": 4.0, "reason": "실력 확인"}, headers=admin)
    assert r.status_code == 200, r.text
    assert _skill(client, club, name)[0] == 4.0
    # 정렬 저장 → 사전값이 다시 계산된다. 오프셋은 남는다 (skill = prior + adjust, 경기 전)
    ids = list(club["pid"].values())
    assert client.post(f"{API}/teams/{club['team_id']}/rankings", json={"player_ids": ids}, headers=club["manager"]).status_code == 201
    skill, prior = _skill(client, club, name)
    with SessionLocal() as db:
        adjust = float(db.get(Player, pid).profile.admin_adjust)
    assert skill == pytest.approx(prior + adjust, abs=0.05) and adjust != 0
    # 쿼터를 저장해도 출발점에 한 번만 더해진다 — 같은 기록을 두 번 재계산해도 값이 같다
    for d in ("2026-09-06", "2026-09-07", "2026-09-08"):
        eid = _event(client, club, d)
        body = {"quarter_no": 1, "black_score": 10, "white_score": 10, "lineups": _lineups(club, TOP5, BOT5)}
        assert client.post(f"{API}/events/{eid}/quarters", json=body, headers=club["manager"]).status_code == 201
    once = _skill(client, club, name)[0]
    from app.services import rating_service

    with SessionLocal() as db:
        rating_service.recompute_team(db, club["team_id"])
        db.commit()
    assert _skill(client, club, name)[0] == once
    # 다시 보정하면 경기 기록이 있어도 원하는 값이 된다
    assert client.patch(f"{API}/admin/players/{pid}/rating", json={"skill_overall": -1.0, "reason": "재보정"}, headers=admin).json()["skill_overall"] == "-1.0"


# ---------------------------------------------------------------------------
# C8 · C14 배정
# ---------------------------------------------------------------------------


# 검증: 한 번의 PATCH 에서 맞교체 뒤 옮기기가 422 면 맞교체도 저장되지 않는다
def test_candidate_edit_is_atomic(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    cand = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()["candidates"][0]
    a = cand["squads"][0]["members"][0]["id"]
    b = cand["squads"][1]["members"][0]["id"]
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": b}], "moves": [{"player_id": a, "to_squad_no": 9}]}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "INVALID_SWAP"
    run = client.get(f"{API}/events/{eid}/assignments", headers=m).json()["items"][0]
    same = next(c for c in run["candidates"] if c["id"] == cand["id"])
    assert same["squads"][0]["members"][0]["id"] == a and not same["metrics"].get("manually_edited")


# 검증: 쿼터 기록이 있는 일정은 배정 실행 · 확정이 422 ASSIGNMENT_LOCKED. 실행 이력에는 제약이 그대로 담긴다
def test_assignment_locked_after_quarters_and_run_history_constraints(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    lock = [club["pid"][TOP5[0]], club["pid"][TOP5[1]]]
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2, "constraints": {"lock_groups": [lock]}}, headers=m).json()
    hist = client.get(f"{API}/events/{eid}/assignments", headers=m).json()["items"]
    c = hist[0]["constraints"]
    assert [sorted(g) for g in c["lock_groups"]] == [sorted(lock)] and c["separate_groups"] == [] and c["pins"] == []
    adopted = run["candidates"][0]
    assert client.post(f"{API}/assignments/candidates/{adopted['id']}:adopt", headers=m).status_code == 200
    sq = adopted["squads"]
    lineups = [{"player_id": p["id"], "side": "BLACK"} for p in sq[0]["members"][:5]] + [{"player_id": p["id"], "side": "WHITE"} for p in sq[1]["members"][:5]]
    assert client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 1, "black_score": 5, "white_score": 3, "lineups": lineups}, headers=m).status_code == 201
    r = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "ASSIGNMENT_LOCKED"
    other = run["candidates"][1]["id"]
    r = client.post(f"{API}/assignments/candidates/{other}:adopt", headers=m)
    assert r.status_code == 422 and r.json()["code"] == "ASSIGNMENT_LOCKED"
    # 쿼터를 지우면 다시 짤 수 있다
    qid = client.get(f"{API}/events/{eid}/quarters", headers=m).json()["items"][0]["id"]
    assert client.delete(f"{API}/quarters/{qid}", headers=m).status_code == 204
    assert client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).status_code == 201


# ---------------------------------------------------------------------------
# D1 점수 상한 · U15 팀 번호
# ---------------------------------------------------------------------------


# 검증: 팀당 쿼터 99점은 1분 쿼터여도 저장되고(정규화 990 < 999.99) 100점은 400. 쿼터 기록에 내 팀 번호가 붙는다
def test_score_cap_and_quarter_record_squad_no(client, club):
    m = club["manager"]
    eid = _event(client, club, "2026-09-13")
    lu = _lineups(club, TOP5, BOT5)
    r = client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 1, "black_score": 100, "white_score": 0, "lineups": lu}, headers=m)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    r = client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 1, "black_score": 99, "white_score": 0, "duration_min": 1, "lineups": lu}, headers=m)
    assert r.status_code == 201, r.text
    assert float(next(x for x in r.json()["lineups"] if x["side"] == "BLACK")["normalized_margin"]) == 990.0
    stats = client.get(f"{API}/players/{club['pid'][BOT5[0]]}/stats", headers=m).json()
    assert stats["recent_quarters"][0]["side"] == "WHITE" and stats["recent_quarters"][0]["squad_no"] == 2


# ---------------------------------------------------------------------------
# C12 · C4 · 게스트 키 · D2 · D3 · D6 · D11
# ---------------------------------------------------------------------------


# 검증: 게스트 수정에서 height_cm 을 빼면 그대로, null 을 보내면 지운다
def test_guest_height_explicit_null_clears(client, club):
    eid, (gid, _) = _event_with_attendance(client, club, guests=2)
    m = club["manager"]
    assert client.patch(f"{API}/events/{eid}/guests/{gid}", json={"height_cm": 185}, headers=m).status_code == 200
    assert client.patch(f"{API}/events/{eid}/guests/{gid}", json={"display_name": "게스트A"}, headers=m).status_code == 200
    with SessionLocal() as db:
        assert db.get(Player, gid).height_cm == 185
    assert client.patch(f"{API}/events/{eid}/guests/{gid}", json={"height_cm": None}, headers=m).status_code == 200
    assert client.patch(f"{API}/players/{gid}", json={"height_cm": 190}, headers=m).status_code == 200
    with SessionLocal() as db:
        assert db.get(Player, gid).height_cm == 190
    assert client.patch(f"{API}/players/{gid}", json={"height_cm": None}, headers=m).status_code == 200
    with SessionLocal() as db:
        assert db.get(Player, gid).height_cm is None


# 검증: 탈퇴하면 이미 나간 팀의 행과 그 행으로 병합된 게스트 행까지 이름 · 키가 지워진다
def test_delete_account_anonymizes_all_rows(client, club, signup):
    m, tid = club["manager"], club["team_id"]
    h = club["members"][5]
    name = ROSTER[5][0]
    my_pid = club["pid"][name]
    eid, (gid, _) = _event_with_attendance(client, club, guests=2)
    client.patch(f"{API}/events/{eid}/guests/{gid}", json={"height_cm": 181}, headers=m)
    assert client.post(f"{API}/players/{gid}:merge", json={"into_player_id": my_pid}, headers=m).status_code == 200
    # 다른 팀에 들어갔다가 나간 상태(LEFT) 행도 만든다
    other = signup("otherteam@example.com", name="다른팀장")
    t2 = client.post(f"{API}/teams", json={"name": "옆팀"}, headers=other).json()
    assert client.post(f"{API}/teams/join", json={"team_code": t2["team_code"]}, headers=h).status_code == 200
    assert client.post(f"{API}/teams/{t2['id']}:leave", headers=h).status_code == 204
    assert client.delete(f"{API}/me", headers=h).status_code == 204
    with SessionLocal() as db:
        uid = db.get(Player, my_pid).user_id
        rows = db.scalars(select(Player).where((Player.user_id == uid) | (Player.id == gid))).all()
        assert len(rows) == 3 and all(p.display_name == "탈퇴한 회원" and p.height_cm is None for p in rows)
    assert tid


# 검증: 카카오 이메일도 소문자로 저장하고 비교한다. DB 는 대문자 이메일을 받지 않는다
def test_kakao_email_normalized_and_db_check(client):
    from app.services import kakao_service
    from app.services.kakao_service import KakaoProfile

    with SessionLocal() as db:
        kakao_service.login_or_signup(db, KakaoProfile(uid="77", nickname="카", profile_image_url=None, email="Mixed@Case.COM"))
        assert db.scalar(select(User.email).where(User.email == "mixed@case.com")) == "mixed@case.com"
        # 이미 있는 이메일과 대소문자만 다르면 이메일 없이 만든다
        kakao_service.login_or_signup(db, KakaoProfile(uid="78", nickname="카2", profile_image_url=None, email="MIXED@case.com"))
        assert db.scalar(select(User.email).join(User.identities).where(User.name == "카2")) is None
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO users (email, name) VALUES ('UP@X.COM', 'u')"))
        db.rollback()


# 검증: 팀마다 활성 정렬은 하나 — 새로 저장하면 이전 것이 꺼지고, DB 도 둘을 허용하지 않는다
def test_single_active_ranking(client, club):
    ids = list(club["pid"].values())
    for _ in range(2):
        assert client.post(f"{API}/teams/{club['team_id']}/rankings", json={"player_ids": ids}, headers=club["manager"]).status_code == 201
    with SessionLocal() as db:
        active = db.scalars(select(ManagerRanking).where(ManagerRanking.team_id == club["team_id"], ManagerRanking.is_active.is_(True))).all()
        assert len(active) == 1
        old = db.scalar(select(ManagerRanking).where(ManagerRanking.is_active.is_(False)))
        old.is_active = True
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
    assert client.post(f"{API}/teams/{club['team_id']}/rankings", json={"player_ids": ids * 51}, headers=club["manager"]).status_code == 400


# 검증: 팀 전술 댓글 · 별표는 team_play_id 로 이어지고, 전술을 지우면 함께 지워진다
def test_team_play_refs_have_fk(client, club):
    from tests.test_team_plays import pnr as _body

    m, tid = club["manager"], club["team_id"]
    r = client.post(f"{API}/teams/{tid}/plays", json=_body(), headers=m)
    assert r.status_code == 201, r.text
    play_id = r.json()["id"]
    key = f"team:{play_id}"
    assert client.post(f"{API}/teams/{tid}/tactics/{key}/comments", json={"body": "좋아요"}, headers=m).status_code == 201
    assert client.put(f"{API}/teams/{tid}/tactics/{key}/star", headers=m).status_code == 200
    assert client.put(f"{API}/teams/{tid}/tactics/{key}/star", headers=m).status_code == 200  # 두 번 달아도 하나
    with SessionLocal() as db:
        assert db.scalar(select(TacticComment.team_play_id)) == play_id
        assert db.scalars(select(TacticStar.team_play_id)).all() == [play_id]
        db.execute(text("DELETE FROM team_plays WHERE id = :i"), {"i": play_id})  # 서비스를 거치지 않아도 FK 가 따라 지운다
        db.commit()
        assert db.scalar(select(TacticComment.id)) is None and db.scalar(select(TacticStar.id)) is None


# ---------------------------------------------------------------------------
# C9 · D7 관리자 콘솔
# ---------------------------------------------------------------------------


# 검증: 콘솔 로그인은 이메일을 정규화하고 요청 제한을 받는다. 참가자 · 일정 · 참석 · 쿼터는 읽기 전용, 사용자 권한 변경은 감사 로그
def test_admin_console_login_and_audit(client, signup):
    import asyncio

    from app import admin_ui
    from app.models import AuditLog

    _make_admin(client, signup)
    assert admin_ui._check_admin_login("admin@hooply.com", "password123") is not None
    assert admin_ui._check_admin_login("admin@hooply.com", "wrong") is None
    assert admin_ui._check_admin_login("nobody@hooply.com", "password123") is None

    class _State:
        pass

    class _FakeRequest:
        def __init__(self, form):
            self._form, self.session, self.headers, self.state = form, {}, {}, _State()
            self.client = type("C", (), {"host": "3.3.3.3"})()

        async def form(self):
            return self._form

    auth = admin_ui.AdminAuth(secret_key="x")
    req = _FakeRequest({"username": "  ADMIN@hooply.com ", "password": "password123"})
    assert asyncio.run(auth.login(req)) is True and req.session["admin_user_id"]
    get_settings().rate_limit_enabled = True
    results = [asyncio.run(auth.login(_FakeRequest({"username": "admin@hooply.com", "password": "bad"}))) for _ in range(ratelimit.ADMIN_LOGIN.limit + 1)]
    assert results == [False] * (ratelimit.ADMIN_LOGIN.limit + 1)
    assert asyncio.run(auth.login(_FakeRequest({"username": "admin@hooply.com", "password": "password123"}))) is False  # 막힌 동안은 맞아도 거부

    for view in (admin_ui.PlayerAdmin, admin_ui.EventAdmin, admin_ui.AttendanceAdmin, admin_ui.QuarterAdmin):
        assert not (view.can_create or view.can_edit or view.can_delete)

    with SessionLocal() as db:
        target = db.scalar(select(User).where(User.email == "admin@hooply.com"))
    view = admin_ui.UserAdmin()
    req = _FakeRequest({})
    req.session["admin_user_id"] = target.id
    asyncio.run(view.on_model_change({}, target, False, req))
    target.global_role = "USER"
    asyncio.run(view.after_model_change({}, target, False, req))
    with SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.target_type == "user"))
        assert log.action == "USER_ROLE_CHANGE" and log.before == {"global_role": "ADMIN"} and log.after == {"global_role": "USER"}
