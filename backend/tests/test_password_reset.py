"""비밀번호 재설정 (FR-02) — 항상 202, 토큰 1회·30분, 새 비밀번호로 로그인, 카카오 전용 계정에 LOCAL 추가."""

from datetime import UTC, datetime, timedelta

from app.services import mail_service

API = "/api/v1"


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(mail_service, "send", lambda to, subject, text, html=None: (sent.append((to, subject, text)) or True))
    return sent


def test_forgot_and_reset(client, signup, monkeypatch):
    sent = _capture(monkeypatch)
    signup("reset@example.com", name="허재", password="oldpassword1")
    # 없는 계정도 202, 메일은 안 감
    assert client.post(f"{API}/auth/password/forgot", json={"email": "nobody@example.com"}).status_code == 202
    assert sent == []
    assert client.post(f"{API}/auth/password/forgot", json={"email": "reset@example.com"}).status_code == 202
    assert len(sent) == 1 and sent[0][0] == "reset@example.com"
    token = sent[0][2].split("token=")[1].split()[0]
    # 잘못된 토큰 / 짧은 비밀번호
    assert client.post(f"{API}/auth/password/reset", json={"token": "wrong", "new_password": "newpassword1"}).json()["code"] == "TOKEN_INVALID_OR_EXPIRED"
    assert client.post(f"{API}/auth/password/reset", json={"token": token, "new_password": "short"}).status_code == 400
    # 정상 재설정 → 새 비밀번호로 로그인, 옛 비밀번호는 실패, 토큰 재사용 불가
    assert client.post(f"{API}/auth/password/reset", json={"token": token, "new_password": "newpassword1"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "reset@example.com", "password": "newpassword1"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "reset@example.com", "password": "oldpassword1"}).status_code == 401
    assert client.post(f"{API}/auth/password/reset", json={"token": token, "new_password": "another123"}).json()["code"] == "TOKEN_INVALID_OR_EXPIRED"


def test_expired_token(client, signup, monkeypatch):
    sent = _capture(monkeypatch)
    signup("exp@example.com", name="서장훈")
    client.post(f"{API}/auth/password/forgot", json={"email": "exp@example.com"})
    token = sent[0][2].split("token=")[1].split()[0]
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models import PasswordResetToken

    with SessionLocal() as db:
        db.execute(update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        db.commit()
    assert client.post(f"{API}/auth/password/reset", json={"token": token, "new_password": "newpassword1"}).json()["code"] == "TOKEN_INVALID_OR_EXPIRED"


def test_kakao_only_account_gets_local_login(client, monkeypatch):
    """카카오로만 가입한 계정(비밀번호 없음)도 이메일이 있으면 재설정으로 비밀번호를 만들 수 있다."""
    sent = _capture(monkeypatch)
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import AuthIdentity, User

    with SessionLocal() as db:
        u = User(email="kakao@example.com", name="이상민", password_hash=None)
        u.identities.append(AuthIdentity(provider="KAKAO", provider_uid="9999", linked_at=datetime.now(UTC)))
        db.add(u); db.commit()
    assert client.post(f"{API}/auth/login", json={"email": "kakao@example.com", "password": "whatever12"}).status_code == 401
    client.post(f"{API}/auth/password/forgot", json={"email": "kakao@example.com"})
    token = sent[0][2].split("token=")[1].split()[0]
    assert client.post(f"{API}/auth/password/reset", json={"token": token, "new_password": "newpassword1"}).status_code == 200
    r = client.post(f"{API}/auth/login", json={"email": "kakao@example.com", "password": "newpassword1"})
    assert r.status_code == 200
    with SessionLocal() as db:
        providers = sorted(i.provider for i in db.scalars(select(AuthIdentity).join(User).where(User.email == "kakao@example.com")).all())
    assert providers == ["KAKAO", "LOCAL"]
