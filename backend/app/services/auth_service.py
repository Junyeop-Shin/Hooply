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

카카오 OAuth(`/auth/kakao/*`)는 kakao_service, 비밀번호 재설정은 이 모듈의 재설정 함수와 mail_service 가 맡는다.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh,
    hash_password,
    verify_password,
)
from app.models import AuthIdentity, Player, RevokedToken, User, UserAvatar
from app.models.enums import AuthProvider, PlayerKind, PlayerStatus, TeamRole
from app.schemas.auth import LoginRequest, SignupRequest, TokenPair


def normalize_email(email: str) -> str:
    """이메일은 대소문자를 구분하지 않는다. 저장·조회 모두 소문자로 (0016 마이그레이션이 기존 행도 맞췄다)."""
    return email.strip().lower()


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
    email = normalize_email(req.email)
    if db.scalar(select(User).where(User.email == email)):
        raise errors.EmailDuplicated()
    user = User(
        email=email,
        password_hash=hash_password(req.password.get_secret_value()),
        name=req.name,
        nickname=req.nickname,
        height_cm=req.height_cm,
    )
    user.identities.append(
        AuthIdentity(provider=AuthProvider.LOCAL, provider_uid=email, linked_at=datetime.now(UTC))
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
    user = db.scalar(select(User).where(User.email == normalize_email(req.email), User.deleted_at.is_(None)))
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
    부수 효과: 쓴 refresh 토큰의 jti 를 폐기 목록에 넣는다 (같은 토큰을 두 번 쓰면 401).
    에러: `401 TOKEN_EXPIRED` (무효·만료·타입 불일치·폐기됨·삭제된 계정 모두).
    """
    maybe_cleanup_tokens(db)
    decoded = decode_refresh(refresh_token)
    if decoded is None:
        raise errors.TokenExpired()
    user_id, jti, exp = decoded
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or db.get(RevokedToken, jti) is not None:
        raise errors.TokenExpired()
    db.add(RevokedToken(jti=jti, user_id=user.id, expires_at=exp))
    db.commit()
    return _issue_tokens(user)


_last_cleanup: float = 0.0
CLEANUP_INTERVAL_SEC = 3600


def cleanup_expired_tokens(db: Session) -> dict[str, int]:
    """만료된 폐기 토큰과 다 쓴(또는 하루 지난) 비밀번호 재설정 토큰을 지운다. 반환: 지운 행 수.

    폐기 목록은 서명 만료가 지나면 어차피 막히므로 남길 이유가 없다. 재설정 토큰은 1회용이라 사용 뒤엔 의미가 없다.
    """
    from datetime import timedelta

    from app.models import PasswordResetToken

    now = datetime.now(UTC)
    revoked = db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now)).rowcount
    reset = db.execute(
        delete(PasswordResetToken).where((PasswordResetToken.used_at.is_not(None)) | (PasswordResetToken.expires_at < now - timedelta(days=1)))
    ).rowcount
    db.commit()
    return {"revoked_tokens": revoked, "password_reset_tokens": reset}


def maybe_cleanup_tokens(db: Session) -> None:
    """토큰 경로(refresh·logout·forgot)에서 한 시간에 한 번만 청소를 돌린다. 별도 스케줄러 없이 쓰레기가 쌓이지 않게."""
    global _last_cleanup
    import time

    now = time.monotonic()
    if now - _last_cleanup < CLEANUP_INTERVAL_SEC:
        return
    _last_cleanup = now
    try:
        cleanup_expired_tokens(db)
    except Exception:
        db.rollback()
        logging.getLogger("hooply").exception("만료 토큰 청소 실패")


def logout(db: Session, refresh_token: str) -> None:
    """refresh 토큰을 폐기한다. 이미 무효한 토큰이면 조용히 넘어간다 (로그아웃은 항상 성공해야 한다)."""
    maybe_cleanup_tokens(db)
    decoded = decode_refresh(refresh_token)
    if decoded is None:
        return
    user_id, jti, exp = decoded
    if db.get(RevokedToken, jti) is None:
        db.add(RevokedToken(jti=jti, user_id=user_id, expires_at=exp))
        db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    """로그인 상태에서 비밀번호 교체. 현재 비밀번호가 맞아야 한다 (기기를 빌린 사람이 바꿔 버리지 못하게)."""
    if user.password_hash is None:
        raise errors.ValidationError("이메일 비밀번호가 없는 계정이에요. 로그인 화면의 '비밀번호 찾기'로 먼저 만들어 주세요.")
    if not verify_password(current, user.password_hash):
        raise errors.InvalidCredentials("현재 비밀번호가 맞지 않아요.")
    user.password_hash = hash_password(new)
    db.commit()


def delete_account(db: Session, user: User) -> None:
    """계정 삭제 (soft delete + 개인정보 비식별화).

    행은 남긴다 — 경기 기록·배정·투표가 players 를 참조하기 때문. 대신 이메일·비밀번호·이름·사진·키·로그인 수단을
    지우고 이름을 '탈퇴한 회원' 으로 바꾼다. 소속 팀에서는 LEFT 처리. 팀에 다른 활성 회원이 있는데 본인이 유일한
    매니저면 먼저 권한을 넘기라고 거부한다 (매니저 없는 팀이 생기지 않게).
    이메일이 비워지므로 같은 이메일로 다시 가입할 수 있다.
    """
    from app.services import team_service

    players = db.scalars(select(Player).where(Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE)).all()
    for p in players:
        if p.role != TeamRole.MANAGER:
            continue
        others = db.scalar(
            select(Player.id).where(Player.team_id == p.team_id, Player.status == PlayerStatus.ACTIVE, Player.kind == PlayerKind.MEMBER, Player.id != p.id).limit(1)
        )
        other_mgr = db.scalar(
            select(Player.id).where(Player.team_id == p.team_id, Player.status == PlayerStatus.ACTIVE, Player.role == TeamRole.MANAGER, Player.id != p.id).limit(1)
        )
        if others is not None and other_mgr is None:
            raise errors.CannotDemoteLastManager(f"'{p.team.name}' 팀의 유일한 매니저예요. 다른 팀원에게 매니저를 넘긴 뒤 탈퇴해 주세요.")
    now = datetime.now(UTC)
    for p in players:
        p.status = PlayerStatus.LEFT
        p.display_name = "탈퇴한 회원"
        team = p.team
        if team.owner_user_id == user.id:
            heir = db.scalar(
                select(Player).where(Player.team_id == team.id, Player.status == PlayerStatus.ACTIVE, Player.role == TeamRole.MANAGER, Player.id != p.id).order_by(Player.id)
            )
            if heir is not None:
                team.owner_user_id = heir.user_id
        db.flush()
        team_service.refresh_team_status(db, team)
    user.deleted_at = now
    user.email = None
    user.password_hash = None
    user.name = "탈퇴한 회원"
    user.nickname = None
    user.profile_image_url = None
    user.height_cm = None
    user.position_prefs = None
    user.primary_team_id = None
    user.identities.clear()
    avatar = db.get(UserAvatar, user.id)
    if avatar is not None:
        db.delete(avatar)
    db.commit()


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

    user = db.scalar(select(User).where(User.email == normalize_email(email), User.deleted_at.is_(None)))
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
