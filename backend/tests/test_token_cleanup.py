"""만료 토큰 청소 — 폐기된 refresh 토큰과 다 쓴 재설정 토큰이 쌓이지 않는다."""

from datetime import UTC, datetime, timedelta

from app.db.session import SessionLocal
from app.models import PasswordResetToken, RevokedToken, User
from app.services import auth_service

API = "/api/v1"


def test_cleanup_removes_expired_and_used_tokens(client, signup):
    signup("t@example.com")
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == "t@example.com").scalar()
        now = datetime.now(UTC)
        db.add_all([
            RevokedToken(jti="expired-1", user_id=uid, expires_at=now - timedelta(minutes=1)),
            RevokedToken(jti="alive-1", user_id=uid, expires_at=now + timedelta(days=7)),
            PasswordResetToken(user_id=uid, token_hash="a" * 64, expires_at=now + timedelta(minutes=30), used_at=now),          # 사용됨
            PasswordResetToken(user_id=uid, token_hash="b" * 64, expires_at=now - timedelta(days=2)),                          # 오래전 만료
            PasswordResetToken(user_id=uid, token_hash="c" * 64, expires_at=now + timedelta(minutes=30)),                      # 유효
        ])
        db.commit()
        removed = auth_service.cleanup_expired_tokens(db)
        assert removed == {"revoked_tokens": 1, "password_reset_tokens": 2}
        assert [r.jti for r in db.query(RevokedToken).all()] == ["alive-1"]
        assert [r.token_hash[0] for r in db.query(PasswordResetToken).all()] == ["c"]
