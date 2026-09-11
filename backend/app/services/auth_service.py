"""이메일/비밀번호 인증 서비스 (설계서 11.5절 · 7.3절 "인증 · 프로필").

이 모듈은 라우터(`app/api/v1/auth.py`)와 DB 사이에서 **계정 생성·로그인·토큰 갱신**의
도메인 규칙을 담당한다. 비밀번호 해시와 JWT 생성 자체는 `app/core/security.py`에 있고,
여기서는 "언제 어떤 에러를 낼 것인가"와 "어떤 행을 만들 것인가"만 결정한다.

설계상 핵심 포인트:
- 로그인 계정(`users`)과 로그인 수단(`auth_identities`)이 분리되어 있다 (6.2절).
  이메일 가입은 `provider=LOCAL`, `provider_uid=email`인 identity를 하나 만든다.
  같은 계정에 나중에 카카오 identity를 추가로 붙일 수 있게 하기 위한 구조다.
- 비밀번호는 bcrypt **단방향 해시**로만 저장한다. 원문은 어디에도 남기지 않는다.
  요청 스키마의 비밀번호가 `SecretStr`이라 `.get_secret_value()`로 꺼내야 한다
  (13.2절 6항: 평문 비밀번호가 로그에 찍히는 사고 방지).
- `users.email`은 NULL 허용이다 (카카오 전용 계정). 그래서 이메일 로그인 경로에서는
  `password_hash is None`인 계정(소셜 전용)을 명시적으로 걸러야 한다.

카카오 OAuth(`/auth/kakao/*`)와 비밀번호 재설정은 아직 라우터에서 501을 반환하며,
이 모듈에는 포함되어 있지 않다.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import AuthIdentity, User
from app.models.enums import AuthProvider
from app.schemas.auth import LoginRequest, SignupRequest, TokenPair


def _issue_tokens(user: User) -> TokenPair:
    """주어진 사용자에게 access/refresh 토큰 한 쌍을 발급한다.

    7.1절 규약대로 access 30분 / refresh 14일 만료이며, 실제 기간은
    `Settings.jwt_access_minutes` / `jwt_refresh_days`에서 읽는다.
    DB를 건드리지 않는 순수 함수다. signup / login / refresh가 공통으로 호출한다.
    """
    return TokenPair(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


def signup(db: Session, req: SignupRequest) -> TokenPair:
    """이메일 회원가입 (FR-01). `POST /auth/signup`.

    처리 순서:
    1. 같은 이메일의 `users` 행이 있으면 거부한다.
    2. `User` 행을 만들고 비밀번호는 bcrypt 해시로 저장한다.
    3. `AuthIdentity(provider=LOCAL, provider_uid=email)`를 함께 붙인다.
       relationship에 append하므로 `db.add(user)` 한 번으로 두 행이 같이 INSERT된다.
    4. 커밋 후 곧바로 토큰을 발급한다 — 가입 직후 별도 로그인 없이 온보딩(S-03)으로
       이어지게 하기 위함이다.

    입력: `SignupRequest` (email, password: SecretStr, name, nickname?, height_cm?)
    출력: `TokenPair`
    부수 효과: `db.commit()` — users 1행 + auth_identities 1행 INSERT.
    에러: `409 EMAIL_DUPLICATED` (이미 가입된 이메일).

    참고: soft delete된 계정(`deleted_at` 설정)도 이메일 UNIQUE 제약에 걸리므로
    같은 이메일로 재가입은 현재 불가하다. 재가입 정책은 아직 미정.
    """
    if db.scalar(select(User).where(User.email == req.email)):
        raise errors.EmailDuplicated()
    user = User(
        email=req.email,
        password_hash=hash_password(req.password.get_secret_value()),
        name=req.name,
        nickname=req.nickname,
        height_cm=req.height_cm,
    )
    user.identities.append(
        AuthIdentity(provider=AuthProvider.LOCAL, provider_uid=req.email, linked_at=datetime.now(UTC))
    )
    db.add(user)
    db.commit()
    return _issue_tokens(user)


def login(db: Session, req: LoginRequest) -> TokenPair:
    """이메일 로그인 (FR-01). `POST /auth/login`.

    이메일로 살아 있는(`deleted_at IS NULL`) 계정을 찾고 bcrypt로 비밀번호를 대조한다.

    다음 세 경우를 **같은 에러**로 뭉뚱그려 응답한다. 어느 단계에서 실패했는지 구분해
    알려주면 "이 이메일은 가입되어 있다"는 사실이 새어 나가기 때문이다.
    - 계정이 없음
    - 계정은 있으나 소셜 전용이라 `password_hash`가 NULL (카카오로만 가입한 사람)
    - 비밀번호 불일치

    입력: `LoginRequest` (email, password: SecretStr)
    출력: `TokenPair`
    부수 효과: 없음 (읽기 전용, 커밋 없음).
    에러: `401 INVALID_CREDENTIALS`.
    """
    user = db.scalar(select(User).where(User.email == req.email, User.deleted_at.is_(None)))
    if user is None or user.password_hash is None:
        raise errors.InvalidCredentials()
    if not verify_password(req.password.get_secret_value(), user.password_hash):
        raise errors.InvalidCredentials()
    return _issue_tokens(user)


def refresh(db: Session, refresh_token: str) -> TokenPair:
    """refresh 토큰으로 새 토큰 쌍을 발급한다. `POST /auth/refresh`.

    `decode_token(..., "refresh")`는 서명·만료·`type` 클레임을 검사하고, 하나라도
    어긋나면 None을 돌려준다. access 토큰을 refresh 자리에 넣는 것도 `type` 불일치로
    막힌다. 토큰이 유효해도 그 사이 계정이 soft delete되었으면 거부한다.

    입력: refresh 토큰 문자열
    출력: `TokenPair` (access·refresh 모두 새로 발급 — 회전 방식)
    부수 효과: 없음. 이전 refresh 토큰을 폐기하는 블랙리스트는 아직 없다.
    에러: `401 TOKEN_EXPIRED` (무효·만료·타입 불일치·삭제된 계정 모두).
    """
    user_id = decode_token(refresh_token, "refresh")
    user = db.get(User, user_id) if user_id else None
    if user is None or user.deleted_at is not None:
        raise errors.TokenExpired()
    return _issue_tokens(user)


# ---------------------------------------------------------------------------
# 비밀번호 재설정 (FR-02, 6.2절 password_reset_tokens)
# ---------------------------------------------------------------------------


def forgot_password(db: Session, email: str) -> None:
    """계정이 있으면 30분짜리 토큰(해시만 저장)을 만들고 링크를 메일로 보낸다. 없으면 아무것도 하지 않는다.

    응답은 호출부가 항상 202 로 고정한다 (계정 존재 여부를 노출하지 않기 위해). 카카오로만 가입해 비밀번호가 없는
    계정도 이 경로로 비밀번호를 만들 수 있다 (reset 이 LOCAL 로그인 수단을 함께 붙인다).
    """
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.security import generate_reset_token
    from app.models import PasswordResetToken
    from app.services import mail_service

    user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None:
        return
    raw, digest = generate_reset_token()
    s = get_settings()
    db.add(PasswordResetToken(user_id=user.id, token_hash=digest, expires_at=datetime.now(UTC) + timedelta(minutes=s.password_reset_minutes)))
    db.commit()
    link = f"{s.frontend_base_url.rstrip('/')}/password/reset?token={raw}"
    mail_service.send_password_reset(user.email, link)


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    """토큰 검증(해시 조회 · 만료 · 1회 사용) 후 비밀번호 교체. 이메일 로그인 수단이 없던 계정에는 LOCAL 을 붙인다."""
    import hashlib

    from app.models import PasswordResetToken

    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == digest))
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at < now:
        raise errors.TokenInvalidOrExpired()
    user = db.get(User, row.user_id)
    if user is None or user.deleted_at is not None or not user.email:
        raise errors.TokenInvalidOrExpired()
    user.password_hash = hash_password(new_password)
    if not any(i.provider == AuthProvider.LOCAL for i in user.identities):
        user.identities.append(AuthIdentity(provider=AuthProvider.LOCAL, provider_uid=user.email, linked_at=now))
    row.used_at = now
    db.commit()
