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

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import errors
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh,
    hash_password,
    verify_password,
)
from app.models import AuditLog, AuthIdentity, Player, RevokedToken, User, UserAvatar
from app.models.enums import AuthProvider, PlayerKind, PlayerStatus, TeamRole
from app.schemas.auth import LoginRequest, SignupRequest, TokenPair

ANON_NAME = "탈퇴한 회원"


def normalize_email(email: str) -> str:
    """이메일은 대소문자를 구분하지 않는다. 저장·조회 모두 소문자로 (0016 마이그레이션이 기존 행도 맞췄다)."""
    return email.strip().lower()


def issue_tokens(user: User) -> TokenPair:
    """주어진 사용자에게 access/refresh 토큰 한 쌍을 발급한다.

    7.1절 규약대로 access 30분 / refresh 14일 만료이며, 실제 기간은
    `Settings.jwt_access_minutes` / `jwt_refresh_days`에서 읽는다. 두 토큰 모두 계정의 현재 세대
    (`users.token_version`)를 싣는다. DB를 건드리지 않는 순수 함수다. signup / login / refresh /
    비밀번호 변경 / 카카오 로그인이 공통으로 호출한다.
    """
    v = user.token_version or 0
    return TokenPair(access_token=create_access_token(user.id, v), refresh_token=create_refresh_token(user.id, v))


_dummy_hash: str | None = None


def _dummy_password_hash() -> str:
    """계정이 없을 때 대신 검증할 bcrypt 해시 (처음 한 번 만든다). 응답 시간으로 가입 여부가 드러나지 않게."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("hooply-timing-equalizer")
    return _dummy_hash


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
    에러: `409 EMAIL_DUPLICATED` (이미 가입된 이메일. 같은 이메일로 동시에 가입해도 하나만 성공하고 나머지는 409).

    참고: 계정을 삭제하면 이메일을 비우므로(`delete_account`) 같은 이메일로 다시 가입할 수 있다.
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
    try:
        db.commit()
    except IntegrityError:  # 검사와 저장 사이에 같은 이메일이 먼저 가입했다
        db.rollback()
        raise errors.EmailDuplicated() from None
    return issue_tokens(user)


def login(db: Session, req: LoginRequest) -> TokenPair:
    """이메일 로그인 (FR-01). `POST /auth/login`.

    이메일로 살아 있는(`deleted_at IS NULL`) 계정을 찾고 bcrypt로 비밀번호를 대조한다.

    다음 세 경우를 **같은 에러**로 뭉뚱그려 응답한다. 어느 단계에서 실패했는지 구분해
    알려주면 "이 이메일은 가입되어 있다"는 사실이 새어 나가기 때문이다.
    - 계정이 없음
    - 계정은 있으나 소셜 전용이라 `password_hash`가 NULL (카카오로만 가입한 사람)
    - 비밀번호 불일치

    계정이 없거나 비밀번호가 없는 계정이어도 가짜 해시로 bcrypt 검증을 한 번 돌린다. 그러지 않으면 "없는 계정"이
    bcrypt 시간(0.2초 남짓)만큼 빨리 실패해 응답 시간으로 가입 여부를 알 수 있다.

    입력: `LoginRequest` (email, password: SecretStr)
    출력: `TokenPair`
    부수 효과: 없음 (읽기 전용, 커밋 없음).
    에러: `401 INVALID_CREDENTIALS`.
    """
    user = db.scalar(select(User).where(User.email == normalize_email(req.email), User.deleted_at.is_(None)))
    password = req.password.get_secret_value()
    if user is None or user.password_hash is None:
        verify_password(password, _dummy_password_hash())
        raise errors.InvalidCredentials()
    if not verify_password(password, user.password_hash):
        raise errors.InvalidCredentials()
    return issue_tokens(user)


def refresh(db: Session, refresh_token: str) -> TokenPair:
    """refresh 토큰으로 새 토큰 쌍을 발급한다. `POST /auth/refresh`.

    `decode_token(..., "refresh")`는 서명·만료·`type` 클레임을 검사하고, 하나라도
    어긋나면 None을 돌려준다. access 토큰을 refresh 자리에 넣는 것도 `type` 불일치로
    막힌다. 토큰이 유효해도 그 사이 계정이 soft delete되었으면 거부한다.

    입력: refresh 토큰 문자열
    출력: `TokenPair` (access·refresh 모두 새로 발급 — 회전 방식)
    부수 효과: 쓴 refresh 토큰의 jti 를 폐기 목록에 넣는다 (같은 토큰을 두 번 쓰면 401). 폐기는
    `INSERT … ON CONFLICT DO NOTHING` 이라 같은 토큰으로 동시에 두 번 갱신해도 하나만 새 쌍을 받고 나머지는 401 이다.
    에러: `401 TOKEN_EXPIRED` (무효·만료·타입 불일치·폐기됨·삭제된 계정·비밀번호 변경 전 세대 모두).
    """
    maybe_cleanup_tokens(db)
    decoded = decode_refresh(refresh_token)
    if decoded is None:
        raise errors.TokenExpired()
    user_id, jti, exp, version = decoded
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or user.token_version != version:
        raise errors.TokenExpired()
    if not _revoke(db, jti, user.id, exp):  # 이미 쓴 토큰 (먼저 온 요청이 폐기했다)
        db.rollback()
        raise errors.TokenExpired()
    db.commit()
    return issue_tokens(user)


def _revoke(db: Session, jti: str, user_id: int, exp: datetime) -> bool:
    """jti 를 폐기 목록에 넣는다. 이번에 넣었으면 True, 이미 있었으면 False (동시 요청에도 하나만 True)."""
    stmt = pg_insert(RevokedToken).values(jti=jti, user_id=user_id, expires_at=exp).on_conflict_do_nothing(index_elements=["jti"])
    return db.execute(stmt.returning(RevokedToken.jti)).first() is not None


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


AUDIT_PII_RETENTION_DAYS = 30  # 탈퇴 뒤 감사 로그에 이메일 · 이름을 남겨 두는 기간
AUDIT_PII_FIELDS = ("email", "name", "nickname")  # 관리자 콘솔 사용자 수정 로그(before/after)에 들어가는 개인정보 키
AUDIT_PII_MASK = "***"


def purge_deleted_user_pii(db: Session) -> int:
    """탈퇴한 지 30일이 지난 계정을 대상으로 한 audit_logs 행에서 이메일 · 이름 · 닉네임을 `***` 로 가린다. 반환: 고친 행 수.

    계정 삭제(delete_account)는 users 행은 바로 비식별화하지만, 관리자 콘솔의 사용자 수정 로그(target_type="user")의
    before/after 스냅샷에는 예전 이메일 · 이름이 그대로 남아 있었다. 30일은 탈퇴 직후의 문의 · 되돌리기 대응에 쓰고,
    그 뒤에는 "무엇이 바뀌었다" 는 사실만 남긴다. 여러 번 돌려도 결과가 같다 (이미 가린 값은 건너뛴다).
    """
    from datetime import timedelta

    from sqlalchemy import String
    from sqlalchemy.dialects.postgresql import array
    from sqlalchemy.orm.attributes import flag_modified

    cutoff = datetime.now(UTC) - timedelta(days=AUDIT_PII_RETENTION_DAYS)
    deleted_ids = select(User.id).where(User.deleted_at.is_not(None), User.deleted_at < cutoff)
    fields = list(AUDIT_PII_FIELDS)
    keys = array(fields, type_=String)  # jsonb ?| text[] — 개인정보 키가 하나라도 있는 행만
    rows = db.scalars(
        select(AuditLog).where(
            AuditLog.target_type == "user", AuditLog.target_id.in_(deleted_ids),
            or_(AuditLog.before.has_any(keys), AuditLog.after.has_any(keys)),
        )
    ).all()
    changed = 0
    for row in rows:
        touched = False
        for attr in ("before", "after"):
            snap = getattr(row, attr)
            if not snap:
                continue
            for f in fields:
                if f in snap and snap[f] not in (None, AUDIT_PII_MASK):
                    snap[f] = AUDIT_PII_MASK
                    touched = True
            if touched:
                flag_modified(row, attr)
        changed += touched
    db.commit()
    return changed


def maybe_cleanup_tokens(db: Session) -> None:
    """토큰 경로(refresh·logout·forgot)에서 한 시간에 한 번만 청소를 돌린다. 별도 스케줄러 없이 쓰레기가 쌓이지 않게.
    만료 토큰과 함께 탈퇴 30일이 지난 계정의 감사 로그 개인정보(purge_deleted_user_pii)도 가린다."""
    global _last_cleanup
    import time

    now = time.monotonic()
    if now - _last_cleanup < CLEANUP_INTERVAL_SEC:
        return
    _last_cleanup = now
    try:
        cleanup_expired_tokens(db)
        purge_deleted_user_pii(db)
    except Exception:
        db.rollback()
        logging.getLogger("hooply").exception("만료 토큰 · 감사 로그 개인정보 청소 실패")


def logout(db: Session, refresh_token: str) -> None:
    """refresh 토큰을 폐기한다. 이미 무효한 토큰이면 조용히 넘어간다 (로그아웃은 항상 성공해야 한다)."""
    maybe_cleanup_tokens(db)
    decoded = decode_refresh(refresh_token)
    if decoded is None:
        return
    user_id, jti, exp, _version = decoded
    if db.get(User, user_id) is None:  # 지워진 계정의 토큰 — 폐기 목록의 외래키를 걸 수 없다
        return
    _revoke(db, jti, user_id, exp)
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> TokenPair:
    """로그인 상태에서 비밀번호 교체. 현재 비밀번호가 맞아야 한다 (기기를 빌린 사람이 바꿔 버리지 못하게).

    토큰 세대(`users.token_version`)를 올려 다른 기기의 로그인을 모두 끊고, 지금 기기가 계속 쓸 새 토큰 쌍을 돌려준다.
    """
    if user.password_hash is None:
        raise errors.ValidationError("이메일 비밀번호가 없는 계정이에요. 로그인 화면의 '비밀번호 찾기'로 먼저 만들어 주세요.")
    if not verify_password(current, user.password_hash):
        raise errors.InvalidCredentials("현재 비밀번호가 맞지 않아요.")
    user.password_hash = hash_password(new)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return issue_tokens(user)


def delete_account(db: Session, user: User) -> None:
    """계정 삭제 (soft delete + 개인정보 비식별화).

    행은 남긴다 — 경기 기록·배정·투표가 players 를 참조하기 때문. 대신 이메일·비밀번호·이름·사진·키·로그인 수단을
    지우고 이름을 '탈퇴한 회원' 으로 바꾼다. 이름 · 키는 이 사람의 모든 players 행(이미 나갔거나 제외된 팀 포함)과
    그 행으로 병합된 게스트 행에서도 지운다 (0026 이 예전 탈퇴자에게도 소급했다). 소속 팀에서는 LEFT 처리.
    팀에 다른 활성 회원이 있는데 본인이 유일한 매니저면 먼저 권한을 넘기라고 거부한다 (매니저 없는 팀이 생기지 않게).
    이메일이 비워지므로 같은 이메일로 다시 가입할 수 있다.

    감사 로그(audit_logs)의 사용자 수정 스냅샷에 남은 이메일 · 이름 · 닉네임은 **탈퇴 30일 뒤** 가린다
    (purge_deleted_user_pii — 시작할 때와 토큰 경로에서 한 시간에 한 번). 그 안에는 문의 · 되돌리기 대응을 위해 남긴다.
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
        team = p.team
        if team.owner_user_id == user.id:
            heir = db.scalar(
                select(Player).where(Player.team_id == team.id, Player.status == PlayerStatus.ACTIVE, Player.role == TeamRole.MANAGER, Player.id != p.id).order_by(Player.id)
            )
            if heir is not None:
                team.owner_user_id = heir.user_id
        db.flush()
        team_service.refresh_team_status(db, team)
    # 비식별화는 상태와 상관없이 모든 행 + 병합된 게스트 행 (위 루프는 활성 소속만 LEFT 로 바꾼다)
    all_ids = select(Player.id).where(Player.user_id == user.id)
    for p in db.scalars(select(Player).where(or_(Player.user_id == user.id, Player.merged_into_player_id.in_(all_ids)))).all():
        p.display_name = ANON_NAME
        p.height_cm = None
    user.deleted_at = now
    user.email = None
    user.password_hash = None
    user.name = ANON_NAME
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


def forgot_password(db: Session, email: str) -> tuple[str, str] | None:
    """계정이 있으면 30분짜리 토큰(해시만 저장)을 만들고 (받는 주소, 링크)를 돌려준다. 없으면 None.

    메일은 호출부(라우터)가 응답을 보낸 뒤 BackgroundTasks 로 보낸다 — 메일 발송 시간이 응답 시간에 섞이면 계정
    존재 여부가 드러난다. 응답은 호출부가 항상 202 로 고정한다. 카카오로만 가입해 비밀번호가 없는 계정도 이 경로로
    비밀번호를 만들 수 있다 (reset 이 LOCAL 로그인 수단을 함께 붙인다).
    """
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.security import generate_reset_token
    from app.models import PasswordResetToken

    user = db.scalar(select(User).where(User.email == normalize_email(email), User.deleted_at.is_(None)))
    if user is None:
        return None
    raw, digest = generate_reset_token()
    s = get_settings()
    db.add(PasswordResetToken(user_id=user.id, token_hash=digest, expires_at=datetime.now(UTC) + timedelta(minutes=s.password_reset_minutes)))
    db.commit()
    link = f"{s.frontend_base_url.rstrip('/')}/password/reset?token={raw}"
    return user.email, link


def reset_password(db: Session, raw_token: str, new_password: str) -> None:
    """토큰 검증(해시 조회 · 만료 · 1회 사용) 후 비밀번호 교체. 이메일 로그인 수단이 없던 계정에는 LOCAL 을 붙인다.

    토큰 세대를 올려 모든 기기의 로그인을 끊는다 (비밀번호를 잊어 재설정하는 상황은 계정 탈취 대응이기도 하다)."""
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
    user.token_version = (user.token_version or 0) + 1
    if not any(i.provider == AuthProvider.LOCAL for i in user.identities):
        user.identities.append(AuthIdentity(provider=AuthProvider.LOCAL, provider_uid=user.email, linked_at=now))
    row.used_at = now
    db.commit()
