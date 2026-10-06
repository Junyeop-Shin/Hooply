"""하드닝 묶음 (0025 ~ 0027): 동시성 409 · 요청 제한 · 토큰 세대 · 운영 키 · 요청 크기 · 관리자 보정 오프셋 ·
배정 잠금 · 쿼터 점수 상한 · 탈퇴 비식별화 · 이메일 소문자 · 활성 정렬 하나 · 팀 전술 FK · 쿼터 기록의 팀 번호 ·
팀 잠금 순서(B1) · 로그인 실패 제한(B3) · 관리자 보정 이력(B4) · 콘솔 읽기 전용 · 세대(B5 · B6) · 프록시 헤더(B7) ·
DB 오류 코드(B8) · 자정 넘김 일정(B11) · 검사 결과의 잠금(B13) · 감사 로그 개인정보(B14)."""

import re
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
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


# 검증: DB 유니크 위반은 409 CONFLICT, 교착 · 직렬화 실패는 같은 코드에 "잠시 뒤 다시" 문구, 외래키 위반은 400 REFERENCE_NOT_FOUND,
# CHECK 위반은 400 VALIDATION_ERROR — 어느 것도 500 으로 새지 않는다
def test_db_errors_map_to_409_and_400():
    app = FastAPI()
    errors.install_error_handlers(app)

    @app.get("/{state}")
    def boom(state: str):
        raise IntegrityError("INSERT …", {}, _Orig(state))

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/23505")
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT" and r.json()["message"] == errors.Conflict.message
    for state in ("40P01", "40001"):
        r = c.get(f"/{state}")
        assert r.status_code == 409 and r.json()["code"] == "CONFLICT" and r.json()["message"] == errors.RETRY_MESSAGE
    r = c.get("/23503")
    assert r.status_code == 400 and r.json()["code"] == "REFERENCE_NOT_FOUND"
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


# 검증: 운영 같은 환경에서만 Cloudflare 의 CF-Connecting-IP(설정 trusted_proxy_header)를 믿는다. 그 밖에는 X-Forwarded-For 의
# **마지막** 값(바로 앞 프록시가 덧붙인 것) → 소켓 주소. 꾸밀 수 있는 첫 값과, 프록시 없는 환경의 CF 헤더는 믿지 않는다
def test_client_ip_trusts_proxy_header_only_in_production(monkeypatch):
    s = get_settings()
    assert not s.is_production_like
    assert ratelimit.client_ip(_Req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9, 2.2.2.2"})) == "2.2.2.2"
    assert ratelimit.client_ip(_Req({"cf-connecting-ip": "1.2.3.4"})) == "10.0.0.1"
    assert ratelimit.client_ip(_Req({"x-forwarded-for": "9.9.9.9, 1.1.1.1"})) == "1.1.1.1"
    assert ratelimit.client_ip(_Req({})) == "10.0.0.1"
    monkeypatch.setattr(s, "app_env", "production")
    assert s.is_production_like
    assert ratelimit.client_ip(_Req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "9.9.9.9, 2.2.2.2"})) == "1.2.3.4"
    assert ratelimit.client_ip(_Req({"true-client-ip": "5.6.7.8"})) == "10.0.0.1"  # 설정한 헤더가 아니면 무시
    monkeypatch.setattr(s, "trusted_proxy_header", "true-client-ip")
    assert ratelimit.client_ip(_Req({"true-client-ip": "5.6.7.8"})) == "5.6.7.8"
    monkeypatch.setattr(s, "trusted_proxy_header", "")
    assert ratelimit.client_ip(_Req({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "3.3.3.3"})) == "3.3.3.3"


# 검증: 창이 지난 키는 훑어 지우고, 키가 너무 많으면 오래된 것부터 버려 90% 로 줄인다. 넘쳐도 1초에 한 번만 훑는다 (요청마다 전체를 훑지 않게)
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
        now[0] += 0.001  # 1초 안에 몰려 들어오면 훑지 않는다 (직전 스윕이 방금 돌았다)
        ratelimit.check(f"x{i}", 5, 60)
    assert len(ratelimit._hits) == 31
    now[0] += ratelimit.MIN_SWEEP_INTERVAL
    ratelimit.check("late", 5, 60)  # 1초가 지나 훑는다 — 가장 오래된 키부터 버려 MAX_KEYS 의 90%(9개)로 줄인 뒤 이번 키를 넣는다
    assert len(ratelimit._hits) == 10 and "late" in ratelimit._hits and "fresh" not in ratelimit._hits and "x29" in ratelimit._hits


# 검증: 비밀번호 찾기는 이메일마다 한 시간에 메일 5통 — 넘으면 429 가 아니라 **조용히** 보내지 않고 202 (남의 이메일로 그 사람의
# 비밀번호 찾기를 막을 수 없게). IP 제한(분당 5회)은 그대로. 가입은 IP 로만 센다 (같은 이메일은 어차피 409)
def test_forgot_silent_mail_cap_and_signup_ip_only(client, signup, monkeypatch):
    from app.services import mail_service

    signup("target@example.com")
    sent: list[str] = []
    monkeypatch.setattr(mail_service, "send_password_reset", lambda to, link: sent.append(to) or True)
    get_settings().rate_limit_enabled = True
    ip = lambda i: {"x-forwarded-for": f"7.7.7.{i}"}  # 프록시가 덧붙인 마지막 값 — 요청마다 다른 IP
    codes = [client.post(f"{API}/auth/password/forgot", json={"email": "Target@Example.com"}, headers=ip(i)).status_code for i in range(ratelimit.FORGOT_MAIL.limit + 3)]
    assert codes == [202] * (ratelimit.FORGOT_MAIL.limit + 3)
    assert len(sent) == ratelimit.FORGOT_MAIL.limit  # 상한을 넘은 요청은 메일을 보내지 않았다
    # 같은 IP 에서 연달아 보내면 IP 제한에 걸린다
    codes = [client.post(f"{API}/auth/password/forgot", json={"email": f"other{i}@example.com"}, headers=ip(99)).status_code for i in range(ratelimit.PASSWORD.limit + 1)]
    assert codes[:-1] == [202] * ratelimit.PASSWORD.limit and codes[-1] == 429
    body = {"email": "dup@example.com", "password": "password123", "name": "x"}
    codes = [client.post(f"{API}/auth/signup", json=body, headers={"x-forwarded-for": f"8.8.8.{i}"}).status_code for i in range(ratelimit.SIGNUP.limit + 1)]
    assert codes[0] == 201 and all(c == 409 for c in codes[1:])  # 이메일로는 세지 않는다
    codes = [client.post(f"{API}/auth/signup", json={**body, "email": f"n{i}@example.com"}, headers={"x-forwarded-for": "8.8.8.8"}).status_code for i in range(ratelimit.SIGNUP.limit + 1)]
    assert codes[:-1] == [201] * ratelimit.SIGNUP.limit and codes[-1] == 429


# 검증: 로그인은 (IP, 이메일) 쌍의 **실패**만 센다 — 공격자 IP 가 남의 이메일로 10번 틀려도 본인은 자기 IP 에서 들어오고,
# 성공하면 그 쌍의 실패 기록이 비워진다. 같은 쌍은 실패 상한을 넘으면 맞는 비밀번호도 429
def test_login_failures_counted_per_ip_email_pair(client, signup):
    signup("victim@example.com")
    get_settings().rate_limit_enabled = True
    attacker, victim = {"x-forwarded-for": "6.6.6.6"}, {"x-forwarded-for": "9.9.9.9"}
    bad = {"email": "victim@example.com", "password": "wrong-password"}
    good = {"email": "victim@example.com", "password": "password123"}
    assert [client.post(f"{API}/auth/login", json=bad, headers=attacker).status_code for _ in range(ratelimit.LOGIN_FAIL.limit)] == [401] * ratelimit.LOGIN_FAIL.limit
    ratelimit.clear("login:ip:6.6.6.6")  # IP 분당 상한이 아니라 (IP, 이메일) 실패 상한이 막는지 본다
    r = client.post(f"{API}/auth/login", json=good, headers=attacker)
    assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED"  # 공격자 IP 에서는 맞아도 막힌다
    assert client.post(f"{API}/auth/login", json=good, headers=victim).status_code == 200  # 본인은 다른 IP 에서 그대로
    # 성공은 세지 않는다 — 같은 IP 에서 여러 번 로그인해도 429 가 아니다 (IP 분당 상한 안에서)
    assert [client.post(f"{API}/auth/login", json=good, headers=victim).status_code for _ in range(ratelimit.LOGIN.limit - 2)] == [200] * (ratelimit.LOGIN.limit - 2)
    # 실패 → 성공 → 실패 기록이 비워져 다시 상한까지 틀릴 수 있다
    ratelimit.reset()
    for _ in range(ratelimit.LOGIN_FAIL.limit - 1):
        assert client.post(f"{API}/auth/login", json=bad, headers=victim).status_code == 401
    assert client.post(f"{API}/auth/login", json=good, headers=victim).status_code == 200
    ratelimit.clear("login:ip:9.9.9.9")  # IP 분당 상한은 이 검증의 대상이 아니다
    assert client.post(f"{API}/auth/login", json=bad, headers=victim).status_code == 401


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
    found = admin_ui._check_admin_login("admin@hooply.com", "password123")
    assert found is not None and found[1] == 0  # (user id, 토큰 세대)
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
    assert asyncio.run(auth.login(req)) is True and req.session["admin_user_id"] and req.session["admin_token_version"] == 0
    assert asyncio.run(auth.authenticate(req)) is True
    # 비밀번호를 바꾸면(세대가 오르면) 로그인해 둔 콘솔 세션도 끝난다
    admin_h = client.post(f"{API}/auth/login", json={"email": "admin@hooply.com", "password": "password123"}).json()
    assert client.post(f"{API}/me/password", json={"current_password": "password123", "new_password": "password456"}, headers={"Authorization": f"Bearer {admin_h['access_token']}"}).status_code == 200
    assert asyncio.run(auth.authenticate(req)) is False
    get_settings().rate_limit_enabled = True
    results = [asyncio.run(auth.login(_FakeRequest({"username": "admin@hooply.com", "password": "bad"}))) for _ in range(ratelimit.ADMIN_LOGIN_FAIL.limit)]
    assert results == [False] * ratelimit.ADMIN_LOGIN_FAIL.limit
    assert asyncio.run(auth.login(_FakeRequest({"username": "admin@hooply.com", "password": "password456"}))) is False  # 실패 상한을 넘으면 맞아도 거부

    for view in (admin_ui.PlayerAdmin, admin_ui.EventAdmin, admin_ui.AttendanceAdmin, admin_ui.QuarterAdmin, admin_ui.LineupAdmin, admin_ui.ProfileAdmin,
                 admin_ui.RunAdmin, admin_ui.CandidateAdmin, admin_ui.SurveyAdmin, admin_ui.VoteAdmin, admin_ui.RankingAdmin, admin_ui.HistoryAdmin, admin_ui.AuditAdmin):
        assert not (view.can_create or view.can_edit or view.can_delete), view

    with SessionLocal() as db:
        target = db.scalar(select(User).where(User.email == "admin@hooply.com"))
    view = admin_ui.UserAdmin()
    req = _FakeRequest({})
    req.session["admin_user_id"] = target.id
    data = {"email": "  Admin@Hooply.COM ", "name": "관리자"}
    asyncio.run(view.on_model_change(data, target, False, req))
    assert data["email"] == "admin@hooply.com"  # 폼의 이메일은 저장 전에 소문자로 (ck_users_email_lower)
    target.global_role = "USER"
    asyncio.run(view.after_model_change({}, target, False, req))
    with SessionLocal() as db:
        log = db.scalar(select(AuditLog).where(AuditLog.target_type == "user"))
        assert log.action == "USER_ROLE_CHANGE" and log.before == {"global_role": "ADMIN"} and log.after == {"global_role": "USER"}


# ---------------------------------------------------------------------------
# B1 팀 잠금 순서
# ---------------------------------------------------------------------------


@contextmanager
def _capture_sql():
    """엔진에 흐르는 SQL 문장을 순서대로 모은다 (BEGIN/COMMIT 은 커서 문장이 아니라 잡히지 않는다)."""
    from sqlalchemy import event as sa_event

    from app.db.session import engine

    log: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        log.append(statement)

    sa_event.listen(engine, "before_cursor_execute", before)
    try:
        yield log
    finally:
        sa_event.remove(engine, "before_cursor_execute", before)


def _assert_lock_before_first_write(log: list[str], label: str) -> None:
    writes = [i for i, s in enumerate(log) if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", s, re.IGNORECASE)]
    locks = [i for i, s in enumerate(log) if "pg_advisory_xact_lock" in s]
    assert writes, f"{label}: 쓰기 문장이 없다"
    assert locks, f"{label}: 팀 잠금을 걸지 않았다"
    assert locks[0] < writes[0], f"{label}: 잠금({locks[0]}) 전에 쓰기({writes[0]})가 있다 — {log[writes[0]][:80]}"


# 검증: 팀 지표를 다시 계산하는 모든 쓰기 경로가 **첫 쓰기 전에** 팀 잠금(pg_advisory_xact_lock)을 건다.
# 행을 먼저 쓰고 재계산 안에서 잠그면, 잠금을 먼저 잡은 다른 요청과 서로를 기다려 교착(40P01 → 409)이 났다
def test_team_lock_taken_before_first_write(client, club, signup):
    m, tid = club["manager"], club["team_id"]
    admin = _make_admin(client, signup)
    eid, (gid, _) = _event_with_attendance(client, club, guests=2)
    cand = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()["candidates"][0]
    assert client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m).status_code == 200
    lu = _lineups(club, TOP5, BOT5)
    q = {"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": lu}
    paths = {
        "쿼터 추가": lambda: client.post(f"{API}/events/{eid}/quarters", json=q, headers=m),
        "쿼터 일괄 저장": lambda: client.put(f"{API}/events/{eid}/quarters", json={"quarters": [q, {**q, "quarter_no": 2}]}, headers=m),
        "쿼터 수정": lambda: client.patch(f"{API}/quarters/{client.get(f'{API}/events/{eid}/quarters', headers=m).json()['items'][0]['id']}", json={"black_score": 12}, headers=m),
        "쿼터 삭제": lambda: client.delete(f"{API}/quarters/{client.get(f'{API}/events/{eid}/quarters', headers=m).json()['items'][-1]['id']}", headers=m),
        "매니저 정렬": lambda: client.post(f"{API}/teams/{tid}/rankings", json={"player_ids": list(club["pid"].values())}, headers=m),
        "자기 위치": lambda: client.put(f"{API}/teams/{tid}/self-rank", json={"level": "TOP10"}, headers=club["members"][3]),
        "게스트 등급": lambda: client.patch(f"{API}/events/{eid}/guests/{gid}", json={"skill_grade": 5}, headers=m),
        "일정 날짜 변경": lambda: client.patch(f"{API}/events/{eid}", json={"event_date": "2026-09-14"}, headers=m),
        "경기 후 투표": lambda: client.post(f"{API}/events/{eid}/post-game-survey", json={"votes": [{"target_player_id": club["pid"][TOP5[1]], "vote_type": "PLAY_AGAIN"}]}, headers=club["members"][0]),
        "게스트 병합": lambda: client.post(f"{API}/players/{gid}:merge", json={"into_player_id": club["pid"][BOT5[4]]}, headers=m),
        "관리자 보정": lambda: client.patch(f"{API}/admin/players/{club['pid'][TOP5[0]]}/rating", json={"skill_overall": 3.0, "reason": "확인"}, headers=admin),
    }
    for label, call in paths.items():
        with _capture_sql() as log:
            r = call()
        assert r.status_code in (200, 201, 204), (label, r.status_code, r.text)
        _assert_lock_before_first_write(log, label)


# 검증: 같은 팀의 두 일정에 쿼터를 동시에 저장해도 교착(409)이 나지 않는다 — 잠금을 먼저 걸어 차례로 처리된다
def test_concurrent_quarter_saves_same_team(client, club):
    m = club["manager"]
    lu = _lineups(club, TOP5, BOT5)
    eids = [_event(client, club, d) for d in ("2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08")]
    codes: list[int] = []
    barrier = threading.Barrier(len(eids))

    def save(eid, i):
        body = {"quarters": [{"quarter_no": n, "black_score": 10 + i, "white_score": 8, "lineups": lu} for n in (1, 2, 3)]}
        barrier.wait()
        codes.append(client.put(f"{API}/events/{eid}/quarters", json=body, headers=m).status_code)

    threads = [threading.Thread(target=save, args=(eid, i)) for i, eid in enumerate(eids)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200] * len(eids), codes


# ---------------------------------------------------------------------------
# B4 관리자 보정 이력
# ---------------------------------------------------------------------------


# 검증: 보정 한 번에 대상의 이력은 ADMIN_ADJUST 한 줄뿐이고(RESIDUAL "경기 기록 반영" 이 덧붙지 않는다), 여파로 바뀐 다른 선수에게는
# "관리자 보정(선수 N) 재계산" 이력이 남으며, 감사 로그에 그 인원수가 적힌다
def test_admin_adjust_history_bookkeeping(client, signup, club):
    from app.models import AuditLog, SkillRatingHistory

    admin = _make_admin(client, signup)
    m = club["manager"]
    for d in ("2026-09-05", "2026-09-06", "2026-09-07"):
        eid = _event(client, club, d)
        assert client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 1, "black_score": 20, "white_score": 5, "lineups": _lineups(club, TOP5, BOT5)}, headers=m).status_code == 201
    pid = club["pid"][TOP5[0]]
    with SessionLocal() as db:
        n_before = db.scalar(select(func.count()).select_from(SkillRatingHistory).where(SkillRatingHistory.player_id == pid))
    assert client.patch(f"{API}/admin/players/{pid}/rating", json={"skill_overall": 4.0, "reason": "실력 확인"}, headers=admin).status_code == 200
    with SessionLocal() as db:
        mine = db.scalars(select(SkillRatingHistory).where(SkillRatingHistory.player_id == pid).order_by(SkillRatingHistory.id)).all()[n_before:]
        assert [h.source for h in mine] == ["ADMIN_ADJUST"] and mine[0].reason == "실력 확인"
        others = db.scalars(select(SkillRatingHistory).where(SkillRatingHistory.ref_type == "admin_adjust")).all()
        assert others and all(o.ref_id == pid and o.player_id != pid and o.reason.startswith(f"관리자 보정(선수 {pid}) 재계산") for o in others)
        log = db.scalar(select(AuditLog).where(AuditLog.action == "ADMIN_RATING_ADJUST").order_by(AuditLog.id.desc()))
        assert log.after["affected_players"] == len({o.player_id for o in others})


# ---------------------------------------------------------------------------
# B10 요청 크기 · 중복 선택지
# ---------------------------------------------------------------------------


# 검증: 설문 응답의 같은 선택지는 하나로(순서 유지), 선택지 · 전술 단계 동작 수에 상한
def test_survey_dedupe_and_step_action_cap():
    from app.schemas.survey import SurveyAnswerIn
    from app.tactics.play import Step

    assert SurveyAnswerIn(question_id=1, selected_option_ids=[3, 1, 3, 2, 1]).selected_option_ids == [3, 1, 2]
    with pytest.raises(ValueError):
        SurveyAnswerIn(question_id=1, selected_option_ids=list(range(21)))
    move = {"slot": 1, "type": "move", "to": {"x": 0.5, "y": 0.5}}
    assert len(Step(caption="x", actions=[move] * 20).actions) == 20
    with pytest.raises(ValueError):
        Step(caption="x", actions=[move] * 21)


# ---------------------------------------------------------------------------
# B11 자정을 넘기는 일정
# ---------------------------------------------------------------------------


# 검증: 22:00~00:30 일정이 저장되고(CHECK · 서비스 검증 없음), 종료 시각은 다음 날 00:30 으로 해석돼 투표도 그때 열린다
def test_event_crossing_midnight(client, club, monkeypatch):
    from datetime import date, time
    from zoneinfo import ZoneInfo

    from app.models import Event
    from app.services import event_service, peer_service

    m, tid = club["manager"], club["team_id"]
    r = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-09-12", "start_time": "22:00", "end_time": "00:30"}, headers=m)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert r.json()["end_time"].startswith("00:30")
    assert client.patch(f"{API}/events/{eid}", json={"end_time": "22:00"}, headers=m).status_code == 200  # 시작 = 종료도 다음 날로
    assert client.patch(f"{API}/events/{eid}", json={"end_time": "00:30"}, headers=m).status_code == 200
    tz = ZoneInfo(get_settings().timezone)
    with SessionLocal() as db:
        ev = db.get(Event, eid)
        assert event_service.ends_at(ev) == datetime(2026, 9, 13, 0, 30, tzinfo=tz)
        assert peer_service.opens_at(ev) == event_service.ends_at(ev)
        ev.end_time = time(23, 0)
        assert event_service.ends_at(ev) == datetime(2026, 9, 12, 23, 0, tzinfo=tz)  # 넘기지 않으면 그날
        ev.end_time = None
        assert event_service.ends_at(ev).date() == date(2026, 9, 12)
    for h in club["members"]:
        client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h)
    fixed = datetime(2026, 9, 13, 0, 10, tzinfo=tz)  # 자정은 넘겼지만 00:30 전 — 아직 안 열린다

    class _Now(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

    monkeypatch.setattr(peer_service, "datetime", _Now)
    assert client.get(f"{API}/events/{eid}/post-game-survey", headers=club["members"][1]).json()["code"] == "SURVEY_NOT_OPEN"
    fixed = datetime(2026, 9, 13, 0, 31, tzinfo=tz)
    assert client.get(f"{API}/events/{eid}/post-game-survey", headers=club["members"][1]).json()["open"] is True


# ---------------------------------------------------------------------------
# B13 검사 결과의 잠금
# ---------------------------------------------------------------------------


# 검증: 쿼터 기록이 있는 일정의 프리플라이트는 422 를 내지 않고 violations 에 ASSIGNMENT_LOCKED 를 담아 feasible=false
def test_validate_reports_assignment_locked(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    assert client.post(f"{API}/events/{eid}/assignments:validate", json={"team_count": 2}, headers=m).json()["feasible"] is True
    assert client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 1, "black_score": 5, "white_score": 3, "lineups": _lineups(club, TOP5, BOT5)}, headers=m).status_code == 201
    r = client.post(f"{API}/events/{eid}/assignments:validate", json={"team_count": 2}, headers=m)
    assert r.status_code == 200
    body = r.json()
    assert body["feasible"] is False and [v["code"] for v in body["violations"]] == ["ASSIGNMENT_LOCKED"]
    assert body["violations"][0]["message"] == errors.AssignmentLocked.message


# ---------------------------------------------------------------------------
# B14 감사 로그 개인정보
# ---------------------------------------------------------------------------


# 검증: 탈퇴 30일이 지난 계정을 대상으로 한 감사 로그의 이메일 · 이름 · 닉네임이 가려진다. 30일 전이거나 살아 있는 계정은 그대로. 여러 번 돌려도 같다
def test_audit_log_pii_purged_after_30_days(client, signup):
    from datetime import timedelta

    from app.models import AuditLog
    from app.services import auth_service

    old = signup("old@example.com", name="옛사람")
    recent = signup("recent@example.com", name="최근사람")
    alive = signup("alive@example.com", name="산사람")
    ids = {e: client.get(f"{API}/me", headers=h).json()["id"] for e, h in (("old", old), ("recent", recent), ("alive", alive))}
    with SessionLocal() as db:
        for key, uid in ids.items():
            db.add(AuditLog(actor_user_id=None, action="USER_UPDATE", target_type="user", target_id=uid,
                            before={"email": f"{key}@example.com", "name": "이름", "global_role": "USER"}, after={"nickname": "별명", "global_role": "ADMIN"}))
        db.add(AuditLog(actor_user_id=None, action="ADMIN_RATING_ADJUST", target_type="player", target_id=1, before={"name": "선수"}, after=None))
        db.commit()
    for h in (old, recent):
        assert client.delete(f"{API}/me", headers=h).status_code == 204
    with SessionLocal() as db:
        db.execute(text("UPDATE users SET deleted_at = :t WHERE id = :i"), {"t": datetime.now(UTC) - timedelta(days=31), "i": ids["old"]})
        db.commit()
        assert auth_service.purge_deleted_user_pii(db) == 1
        assert auth_service.purge_deleted_user_pii(db) == 0  # 두 번째는 할 일이 없다
        rows = {r.target_id: r for r in db.scalars(select(AuditLog).where(AuditLog.target_type == "user")).all()}
        assert rows[ids["old"]].before == {"email": "***", "name": "***", "global_role": "USER"} and rows[ids["old"]].after == {"nickname": "***", "global_role": "ADMIN"}
        assert rows[ids["recent"]].before["email"] == "recent@example.com" and rows[ids["alive"]].before["email"] == "alive@example.com"
        assert db.scalar(select(AuditLog.before).where(AuditLog.target_type == "player")) == {"name": "선수"}
