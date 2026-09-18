"""계정 보안·관리: 이메일 정규화 · 요청 제한 · 로그아웃(refresh 폐기) · 비밀번호 변경 · 계정 삭제 · 팀 나가기."""

import pytest

from app.core import ratelimit
from app.core.config import get_settings

API = "/api/v1"


def _login(client, email, password="password123"):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


# 검증: 이메일은 대소문자를 구분하지 않는다 — 다른 표기로 두 계정이 생기지 않고, 어느 표기로도 로그인된다
def test_email_is_case_insensitive(client, signup):
    signup("Case.User@Example.com")
    assert _login(client, "case.user@example.com").status_code == 200
    assert _login(client, "CASE.USER@EXAMPLE.COM").status_code == 200
    r = client.post(f"{API}/auth/signup", json={"email": "case.user@EXAMPLE.com", "password": "password123", "name": "x"})
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_DUPLICATED"
    me = client.get(f"{API}/me", headers=signup("Other@Example.com")).json()
    assert me["email"] == "other@example.com"  # 저장도 소문자


# 검증: 로그인 시도가 분당 상한을 넘으면 429 RATE_LIMITED (IP 기준). 테스트 기본값은 꺼져 있어 여기서만 켠다
def test_login_rate_limit(client, signup):
    signup("victim@example.com")
    get_settings().rate_limit_enabled = True
    ratelimit.reset()
    try:
        codes = [_login(client, "victim@example.com", "wrong-password").status_code for _ in range(ratelimit.LOGIN.limit + 2)]
        assert codes[: ratelimit.LOGIN.limit] == [401] * ratelimit.LOGIN.limit
        assert codes[ratelimit.LOGIN.limit] == 429
        r = _login(client, "victim@example.com")  # 맞는 비밀번호여도 창이 닫히기 전엔 막힌다
        assert r.status_code == 429 and r.json()["code"] == "RATE_LIMITED"
    finally:
        get_settings().rate_limit_enabled = False
        ratelimit.reset()


# 검증: 로그아웃하면 refresh 토큰이 폐기되고, 재발급에 쓴 refresh 토큰은 다시 쓸 수 없다 (회전)
def test_logout_revokes_refresh_and_rotation(client, signup):
    signup("r@example.com")
    pair = _login(client, "r@example.com").json()
    # 회전: 한 번 쓴 refresh 는 폐기
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 200
    new_pair = r.json()
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    # 로그아웃: 그 뒤 재발급 불가, 토큰이 무효해도 204
    assert client.post(f"{API}/auth/logout", json={"refresh_token": new_pair["refresh_token"]}).status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": new_pair["refresh_token"]}).status_code == 401
    assert client.post(f"{API}/auth/logout", json={"refresh_token": "garbage"}).status_code == 204


# 검증: 비밀번호 변경은 현재 비밀번호가 맞아야 하고, 바꾼 뒤에는 새 비밀번호로만 로그인된다
def test_change_password(client, signup):
    h = signup("p@example.com")
    r = client.post(f"{API}/me/password", json={"current_password": "nope-nope", "new_password": "newpassword1"}, headers=h)
    assert r.status_code == 401 and r.json()["code"] == "INVALID_CREDENTIALS"
    assert client.post(f"{API}/me/password", json={"current_password": "password123", "new_password": "short"}, headers=h).status_code == 400
    assert client.post(f"{API}/me/password", json={"current_password": "password123", "new_password": "newpassword1"}, headers=h).status_code == 204
    assert _login(client, "p@example.com", "password123").status_code == 401
    assert _login(client, "p@example.com", "newpassword1").status_code == 200


# 검증: 계정 삭제 — 로그인·토큰이 막히고, 개인정보가 지워지고, 팀에서 나가며, 같은 이메일로 다시 가입할 수 있다
def test_delete_account(client, signup):
    owner = signup("owner@example.com", name="팀장")
    tid = client.post(f"{API}/teams", json={"name": "삭제팀"}, headers=owner).json()["id"]
    code = client.get(f"{API}/teams/{tid}", headers=owner).json()["team_code"]
    member = signup("gone@example.com", name="나갈사람")
    assert client.post(f"{API}/teams/join", json={"team_code": code}, headers=member).status_code == 200
    pair = _login(client, "gone@example.com").json()

    assert client.delete(f"{API}/me", headers=member).status_code == 204
    assert client.get(f"{API}/me", headers=member).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401
    assert _login(client, "gone@example.com").status_code == 401
    names = [p["display_name"] for p in client.get(f"{API}/teams/{tid}/players", headers=owner).json()["items"]]
    assert "나갈사람" not in names
    left = client.get(f"{API}/teams/{tid}/players?status=LEFT", headers=owner).json()["items"]
    assert any(p["display_name"] == "탈퇴한 회원" for p in left)  # 기록용 행은 비식별화돼 남는다
    assert client.post(f"{API}/auth/signup", json={"email": "gone@example.com", "password": "password123", "name": "다시"}).status_code == 201

    # 다른 팀원이 있는 팀의 유일한 매니저는 삭제 전에 권한을 넘겨야 한다
    stay = signup("stay@example.com", name="남는사람")
    assert client.post(f"{API}/teams/join", json={"team_code": code}, headers=stay).status_code == 200
    r = client.delete(f"{API}/me", headers=owner)
    assert r.status_code == 422 and r.json()["code"] == "CANNOT_DEMOTE_LAST_MANAGER"


# 검증: 팀 나가기 — 일반 팀원은 나갈 수 있고, 유일한 매니저는 다른 팀원이 있으면 못 나간다
def test_leave_team(client, signup):
    owner = signup("o2@example.com", name="팀장")
    tid = client.post(f"{API}/teams", json={"name": "나가기팀"}, headers=owner).json()["id"]
    code = client.get(f"{API}/teams/{tid}", headers=owner).json()["team_code"]
    m = signup("m2@example.com", name="팀원")
    client.post(f"{API}/teams/join", json={"team_code": code}, headers=m)

    r = client.post(f"{API}/teams/{tid}:leave", headers=owner)
    assert r.status_code == 422 and r.json()["code"] == "CANNOT_DEMOTE_LAST_MANAGER"
    assert client.post(f"{API}/teams/{tid}:leave", headers=m).status_code == 204
    assert client.get(f"{API}/teams/{tid}", headers=m).status_code == 403  # 더는 팀원이 아니다
    assert all(t["team_id"] != tid for t in client.get(f"{API}/me/teams", headers=m).json()["items"])
    # 마지막 사람(매니저)은 나갈 수 있고, 팀 코드로 다시 들어오면 복원된다
    assert client.post(f"{API}/teams/{tid}:leave", headers=owner).status_code == 204
    assert client.post(f"{API}/teams/join", json={"team_code": code}, headers=m).status_code == 200


@pytest.fixture(autouse=True)
def _limits_off():
    ratelimit.reset()
    yield
    ratelimit.reset()
