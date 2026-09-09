"""카카오 로그인 (11.5절) — 인가 URL·state, 콜백 가입/로그인, 계정 연결. 카카오 서버 호출은 monkeypatch 로 대체."""

import pytest

from app.core.config import get_settings
from app.services import kakao_service
from app.services.kakao_service import KakaoProfile

API = "/api/v1"


@pytest.fixture(autouse=True)
def kakao_config(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "kakao_client_id", "test-client-id")
    monkeypatch.setattr(s, "kakao_redirect_uri", "http://localhost:5173/auth/kakao/callback")
    profiles = {"code-a": KakaoProfile(uid="1001", nickname="허재", profile_image_url="https://k.kakaocdn.net/a.jpg", email=None),
                "code-b": KakaoProfile(uid="2002", nickname="서장훈", profile_image_url=None, email="seo@example.com")}

    def fake_fetch(code, redirect_uri):
        if code not in profiles:
            raise kakao_service.errors.KakaoAuthFailed("bad code")
        return profiles[code]

    monkeypatch.setattr(kakao_service, "fetch_profile", fake_fetch)
    yield


# 검증: 11.5절 1단계 — 인가 URL 에 client_id·redirect_uri·state 가 들어가고, 허용되지 않은 redirect_uri 는 401
def test_login_url_and_redirect_allowlist(client):
    r = client.get(f"{API}/auth/kakao/login-url")
    assert r.status_code == 200
    body = r.json()
    assert body["url"].startswith("https://kauth.kakao.com/oauth/authorize?") and "client_id=test-client-id" in body["url"] and body["state"] in body["url"]
    assert client.get(f"{API}/auth/kakao/login-url?redirect_uri=https://evil.example/cb").status_code == 401
    assert client.get(f"{API}/auth/kakao/login-url?redirect_uri=http://localhost:5173/auth/kakao/callback").status_code == 200  # CORS 출처 기반 허용


# 검증: 11.5절 2~6단계 — 첫 콜백은 가입(is_new, 이메일 없는 계정), 두 번째는 로그인. state 위조·만료는 401
def test_callback_signup_then_login(client):
    state = client.get(f"{API}/auth/kakao/login-url").json()["state"]
    r = client.get(f"{API}/auth/kakao/callback?code=code-a&state={state}")
    assert r.status_code == 200, r.text
    assert r.json()["is_new"] is True and r.json()["access_token"]
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get(f"{API}/me", headers=h).json()
    assert me["email"] is None and me["name"] == "허재" and me["onboarding_completed"] is False
    assert [i["provider"] for i in me["identities"]] == ["KAKAO"]
    # 같은 회원번호로 다시 → 로그인 (새 계정 없음)
    state2 = client.get(f"{API}/auth/kakao/login-url").json()["state"]
    r2 = client.get(f"{API}/auth/kakao/callback?code=code-a&state={state2}")
    assert r2.status_code == 200 and r2.json()["is_new"] is False
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {r2.json()['access_token']}"}).json()["id"] == me["id"]
    # state 위조 / 잘못된 코드
    assert client.get(f"{API}/auth/kakao/callback?code=code-a&state=forged").status_code == 401
    assert client.get(f"{API}/auth/kakao/callback?code=nope&state={state2}").status_code == 401
    # 이메일 계정과 같은 이메일을 가진 카카오 계정은 이메일 없이 만들어진다 (5.4절 동일인 중복 가입 → 병합으로 해결)
    client.post(f"{API}/auth/signup", json={"email": "seo@example.com", "password": "password123", "name": "서장훈"})
    r3 = client.get(f"{API}/auth/kakao/callback?code=code-b&state={client.get(f'{API}/auth/kakao/login-url').json()['state']}")
    assert r3.status_code == 200 and r3.json()["is_new"] is True
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {r3.json()['access_token']}"}).json()["email"] is None


# 검증: 6.2절 auth_identities 1:N — 이메일 계정에 카카오 연결, 다른 계정에 이미 연결된 회원번호는 409
def test_link(client, signup):
    h = signup("mail@example.com", name="이상민")
    state = client.get(f"{API}/auth/kakao/login-url").json()["state"]
    r = client.post(f"{API}/auth/kakao/link", json={"code": "code-a", "state": state}, headers=h)
    assert r.status_code == 200, r.text
    assert sorted(i["provider"] for i in r.json()["identities"]) == ["KAKAO", "LOCAL"]
    # 이제 카카오로 로그인하면 같은 계정
    state2 = client.get(f"{API}/auth/kakao/login-url").json()["state"]
    r2 = client.get(f"{API}/auth/kakao/callback?code=code-a&state={state2}")
    assert r2.json()["is_new"] is False and client.get(f"{API}/me", headers={"Authorization": f"Bearer {r2.json()['access_token']}"}).json()["email"] == "mail@example.com"
    # 다른 계정이 같은 카카오를 연결하려 하면 409
    h2 = signup("other@example.com", name="현주엽")
    r3 = client.post(f"{API}/auth/kakao/link", json={"code": "code-a", "state": client.get(f"{API}/auth/kakao/login-url").json()["state"]}, headers=h2)
    assert r3.status_code == 409 and r3.json()["code"] == "IDENTITY_ALREADY_LINKED"
