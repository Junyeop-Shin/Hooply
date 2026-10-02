"""카카오 로그인 (11.5절) — 인가 URL 생성, 인가 코드 → 토큰 교환 → 프로필 조회, 가입/로그인/계정 연결.

흐름 (프론트 ↔ 이 서비스 ↔ 카카오)
1. 프론트가 `GET /auth/kakao/login-url?redirect_uri=` 로 인가 URL 을 받아 브라우저를 이동시킨다.
   `state` 는 서버가 서명한 10분짜리 토큰이라 세션 저장소 없이도 콜백에서 위조 여부를 검증할 수 있다.
2. 카카오가 `redirect_uri?code=&state=` 로 돌려보내면 프론트가 `GET /auth/kakao/callback` 에 그대로 넘긴다.
3. 서버가 코드를 카카오 토큰으로 바꾸고(`kauth.kakao.com/oauth/token`) 회원번호·닉네임·프로필 사진을 읽는다
   (`kapi.kakao.com/v2/user/me`). 이메일은 비즈 앱 전환 전에는 오지 않으므로 없어도 가입된다 (users.email NULL).
4. `auth_identities(provider=KAKAO, provider_uid=회원번호)` 가 있으면 로그인, 없으면 계정 생성 → 우리 JWT 발급.

`redirect_uri` 는 프론트가 자기 출처 기준으로 보내되, 설정된 값(KAKAO_REDIRECT_URI) 또는 CORS 허용 출처의
`/auth/kakao/callback` 만 받아 준다 (오픈 리다이렉트 방지). 토큰 교환 때도 같은 값을 카카오에 보내야 한다.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.core.config import get_settings
from app.models import AuthIdentity, User, UserAvatar
from app.models.enums import AuthProvider
from app.schemas.auth import TokenPair
from app.services.auth_service import issue_tokens, normalize_email

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
ME_URL = "https://kapi.kakao.com/v2/user/me"
STATE_TTL = timedelta(minutes=10)
CALLBACK_PATH = "/auth/kakao/callback"


@dataclass
class KakaoProfile:
    uid: str  # 카카오 회원번호 (문자열)
    nickname: str | None
    profile_image_url: str | None
    email: str | None


def _configured() -> None:
    if not get_settings().kakao_client_id:
        raise errors.KakaoAuthFailed("카카오 로그인을 아직 쓸 수 없어요.")


def resolve_redirect_uri(requested: str | None) -> str:
    """프론트가 보낸 redirect_uri 를 허용 목록과 대조한다. 없으면 설정값."""
    s = get_settings()
    allowed = {s.kakao_redirect_uri} | {origin.rstrip("/") + CALLBACK_PATH for origin in s.cors_origins}
    allowed.discard("")
    if requested is None:
        if not s.kakao_redirect_uri:
            raise errors.KakaoAuthFailed("카카오 로그인을 아직 쓸 수 없어요.")
        return s.kakao_redirect_uri
    if requested not in allowed:
        raise errors.KakaoAuthFailed("허용되지 않은 주소예요.")
    return requested


def make_state() -> str:
    """CSRF 방지 state — 서버 서명 토큰 (11.5절 '반드시 지켜야 할 것' 4항). 세션 저장소가 필요 없다."""
    s = get_settings()
    now = datetime.now(UTC)
    return jwt.encode({"type": "kakao_state", "nonce": secrets.token_urlsafe(16), "iat": now, "exp": now + STATE_TTL}, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def verify_state(state: str) -> None:
    s = get_settings()
    try:
        payload = jwt.decode(state, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    except JWTError:
        raise errors.KakaoAuthFailed("로그인 요청이 만료됐어요. 다시 시도해 주세요.") from None
    if payload.get("type") != "kakao_state":
        raise errors.KakaoAuthFailed("로그인 요청이 올바르지 않아요. 다시 시도해 주세요.")


def login_url(redirect_uri: str | None) -> tuple[str, str]:
    _configured()
    uri = resolve_redirect_uri(redirect_uri)
    state = make_state()
    q = urlencode({"client_id": get_settings().kakao_client_id, "redirect_uri": uri, "response_type": "code", "state": state})
    return f"{AUTHORIZE_URL}?{q}", state


def fetch_profile(code: str, redirect_uri: str) -> KakaoProfile:
    """인가 코드 → 액세스 토큰 → 프로필. 테스트에서는 이 함수를 monkeypatch 한다."""
    s = get_settings()
    data = {"grant_type": "authorization_code", "client_id": s.kakao_client_id, "redirect_uri": redirect_uri, "code": code}
    if s.kakao_client_secret:
        data["client_secret"] = s.kakao_client_secret
    try:
        with httpx.Client(timeout=10) as client:
            tok = client.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
            if tok.status_code != 200:
                raise errors.KakaoAuthFailed("카카오 로그인에 실패했어요. 다시 시도해 주세요.")
            me = client.get(ME_URL, headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
            if me.status_code != 200:
                raise errors.KakaoAuthFailed("카카오에서 프로필을 받지 못했어요.")
    except httpx.HTTPError:
        raise errors.KakaoAuthFailed("카카오에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.") from None
    body = me.json()
    account = body.get("kakao_account") or {}
    profile = account.get("profile") or {}
    return KakaoProfile(
        uid=str(body["id"]), nickname=profile.get("nickname"), profile_image_url=profile.get("profile_image_url"),
        email=account.get("email") if account.get("is_email_valid", True) else None,
    )


def _identity(db: Session, uid: str) -> AuthIdentity | None:
    return db.scalar(select(AuthIdentity).where(AuthIdentity.provider == AuthProvider.KAKAO, AuthIdentity.provider_uid == uid))


def login_or_signup(db: Session, p: KakaoProfile) -> tuple[TokenPair, bool]:
    """회원번호로 계정을 찾아 로그인, 없으면 가입. 반환 (토큰, 신규 여부)."""
    ident = _identity(db, p.uid)
    if ident is not None:
        user = db.get(User, ident.user_id)
        if user is None or user.deleted_at is not None:
            raise errors.KakaoAuthFailed("탈퇴한 계정이에요.")
        # 카카오 CDN 주소는 바뀔 수 있으므로 로그인 때마다 새로 받는다 (11.5절 3항).
        # 단, 직접 올린 사진이 있으면 건드리지 않는다 — 예전에는 여기서 덮어써서 올린 사진이 로그인 한 번에 사라졌다.
        if p.profile_image_url and db.get(UserAvatar, user.id) is None:
            user.profile_image_url = p.profile_image_url
        db.commit()
        return issue_tokens(user), False
    email = normalize_email(p.email) if p.email else None  # 이메일 가입과 같은 규칙(소문자)으로 저장 · 비교한다
    if email and db.scalar(select(User.id).where(User.email == email)):
        email = None  # 같은 이메일의 이메일 계정이 이미 있으면 충돌을 피해 이메일 없이 만든다 (5.4절 POSSIBLE_DUPLICATE 는 병합으로 해결)
    name = (p.nickname or "카카오 회원")[:50]
    user = User(email=email, password_hash=None, name=name, nickname=p.nickname[:50] if p.nickname else None, profile_image_url=p.profile_image_url)
    user.identities.append(AuthIdentity(provider=AuthProvider.KAKAO, provider_uid=p.uid, linked_at=datetime.now(UTC)))
    db.add(user)
    db.commit()
    db.refresh(user)
    return issue_tokens(user), True


def link(db: Session, user: User, p: KakaoProfile) -> User:
    """이미 로그인한 계정에 카카오 연결. 그 회원번호가 다른 계정에 있으면 409."""
    ident = _identity(db, p.uid)
    if ident is not None:
        if ident.user_id == user.id:
            return user
        raise errors.IdentityAlreadyLinked()
    db.add(AuthIdentity(user_id=user.id, provider=AuthProvider.KAKAO, provider_uid=p.uid, linked_at=datetime.now(UTC)))
    if not user.profile_image_url and p.profile_image_url and db.get(UserAvatar, user.id) is None:
        user.profile_image_url = p.profile_image_url
    db.commit()
    db.refresh(user)
    return user
