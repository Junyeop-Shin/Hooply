"""11.5절: 비밀번호는 bcrypt 단방향 해시, 토큰은 JWT (access 30분 / refresh 14일).

이 모듈에는 DB 나 HTTP 를 모르는 순수 함수만 둔다. 호출하는 쪽:

- 비밀번호 해시/검증  → app/services/auth_service.py (가입·로그인)
- JWT 발급            → auth_service (로그인·refresh 응답의 TokenPair)
- JWT 검증            → app/api/deps.py `get_current_user` (access), auth_service (refresh)
- 팀 코드 생성        → app/services/team_service.py (팀 생성·코드 재발급)
- 재설정 토큰 생성    → 비밀번호 찾기 (auth_service.forgot_password)

--- 비밀번호: "암호화"가 아니라 "해시"다 (11.5절 질문 1) ---
암호화는 키만 있으면 되돌릴 수 있지만, 해시는 원리적으로 되돌릴 수 없다. 로그인 검증에는
원문이 필요 없다 — 입력값을 같은 방식으로 해시해 저장된 해시와 비교하면 되기 때문이다.
그래서 서비스는 사용자의 비밀번호 원문을 절대 알지 못하고, DB 가 통째로 유출돼도 복원되지 않는다.

bcrypt 를 쓰는 이유: SHA-256 같은 범용 해시는 너무 빨라서 대입 공격에 취약하다. bcrypt 는
의도적으로 느리고(검증에 0.2~0.3초), 솔트가 자동으로 붙어 같은 비밀번호도 매번 다른 해시가 된다.
bcrypt 는 입력을 72바이트까지만 반영하므로 요청 스키마의 `max_length=72` 는 이 한계에서 온 것이다.

--- 토큰 ---
access 토큰은 API 호출마다 `Authorization: Bearer ...` 로 보내는 짧은 토큰, refresh 토큰은
access 가 만료됐을 때 새 쌍을 받기 위한 긴 토큰이다. 둘은 같은 방식으로 서명되지만 payload 의
`type` 클레임이 다르고, 검증할 때 이 값을 반드시 대조한다 (`decode_token` 참고).

--- 비밀번호 재설정 토큰 ---
DB 에는 원문이 아니라 SHA-256 해시만 저장한다 (`password_reset_tokens.token_hash`). 원문은
메일로 사용자에게만 전달된다. 여기서는 bcrypt 가 아니라 SHA-256 을 써도 되는데, 토큰이 32바이트
난수라 사전 공격이 성립하지 않기 때문이다 (사람이 고른 비밀번호와 다르다).
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# passlib 컨텍스트. schemes=["bcrypt"] 하나만 쓰고, deprecated="auto" 는 나중에 Argon2 등으로
# 바꿀 때 기존 bcrypt 해시를 자동으로 "구식"으로 표시해 재해시를 유도하기 위한 옵션이다.
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """평문 비밀번호 → bcrypt 해시 문자열 (가입·비밀번호 변경 시 DB 에 저장할 값).

    같은 입력이라도 호출할 때마다 솔트가 달라 결과가 다르다. 그래서 "해시가 같은가"가 아니라
    `verify_password` 로 비교해야 한다. 결과는 `users.password_hash` (VARCHAR(255)) 에 들어간다.
    """
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """로그인 시 입력한 평문이 저장된 해시와 일치하는지. 일치하면 True.

    호출부(auth_service)는 False 일 때 `INVALID_CREDENTIALS` 를 던진다. 이메일이 없을 때와
    같은 에러를 내서 계정 존재 여부를 드러내지 않는다.
    """
    return _pwd.verify(plain, hashed)


def _create_token(subject: int, token_type: str, expires: timedelta, version: int = 0) -> str:
    """JWT 를 만든다. access / refresh 공통 구현.

    payload:
      sub  — user_id 를 문자열로 (JWT 표준상 sub 는 문자열)
      type — "access" | "refresh". 종류를 구분하는 우리만의 클레임
      ver  — 토큰 세대 (`users.token_version`). 비밀번호를 바꾸면 올라가 예전 세대의 토큰이 모두 막힌다
      iat  — 발급 시각(UTC)
      exp  — 만료 시각(UTC). python-jose 가 decode 시 자동으로 검사한다
    """
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(subject), "type": token_type, "ver": version, "iat": now, "exp": now + expires}
    if token_type == "refresh":
        payload["jti"] = str(uuid.uuid4())  # 폐기 목록(revoked_tokens)의 키. 로그아웃·회전 때 이 값을 기록한다
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def create_access_token(user_id: int, version: int = 0) -> str:
    """access 토큰 (기본 30분, `Settings.jwt_access_minutes`). `TokenPair.access_token`."""
    return _create_token(user_id, "access", timedelta(minutes=get_settings().jwt_access_minutes), version)


def create_refresh_token(user_id: int, version: int = 0) -> str:
    """refresh 토큰 (기본 14일, `Settings.jwt_refresh_days`). `TokenPair.refresh_token`."""
    return _create_token(user_id, "refresh", timedelta(days=get_settings().jwt_refresh_days), version)


def _version(payload: dict) -> int:
    """`ver` 클레임. 이 클레임이 생기기 전에 발급된 토큰은 0 세대로 본다 (비밀번호를 바꾸기 전까지 그대로 쓰인다)."""
    try:
        return int(payload.get("ver", 0))
    except (TypeError, ValueError):
        return -1  # 어떤 계정의 세대와도 맞지 않게


def decode_token(token: str, expected_type: str) -> tuple[int, int] | None:
    """유효하면 (user_id, 토큰 세대), 아니면 None. 세대가 계정과 맞는지는 호출자(deps.get_current_user)가 본다.

    None 이 되는 경우: 서명 불일치(위조·키 변경), 만료, 형식 오류, `type` 클레임이 기대와 다름,
    `sub` 가 없거나 정수가 아님. 이유를 구분하지 않고 전부 None 으로 뭉개는 것은 의도다 —
    호출부는 어느 경우든 `TOKEN_EXPIRED` 로 응답하면 되고, 공격자에게 힌트를 주지 않는다.

    `expected_type` 대조가 중요한 이유: refresh 토큰은 14일짜리라 유출 시 피해가 크다. 이 검사가
    없으면 refresh 토큰을 Authorization 헤더에 넣어 access 토큰처럼 14일 동안 API 를 부를 수 있다.
    반대로 access 토큰으로 refresh 를 시도하는 것도 막는다.
      - deps.get_current_user  → decode_token(token, "access")
      - auth_service.refresh   → decode_token(token, "refresh")
    """
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    try:
        return int(payload["sub"]), _version(payload)
    except (KeyError, ValueError):
        return None


def decode_refresh(token: str) -> tuple[int, str, datetime, int] | None:
    """refresh 토큰 → (user_id, jti, 만료 시각, 토큰 세대). 서명·만료·type 이 어긋나거나 jti 가 없으면 None."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("type") != "refresh" or not payload.get("jti"):
        return None
    try:
        return int(payload["sub"]), str(payload["jti"]), datetime.fromtimestamp(int(payload["exp"]), tz=UTC), _version(payload)
    except (KeyError, ValueError, TypeError):
        return None


def generate_team_code(length: int = 8) -> str:
    """대문자+숫자 (혼동되는 0/O/1/I 제외).

    `teams.team_code` CHAR(8) UNIQUE 에 들어갈 값. 카카오톡으로 공유하고 손으로 입력하는 코드라
    글꼴에 따라 헷갈리는 글자를 뺐다. 32글자 × 8자리 = 약 1조 가지라 충돌은 거의 없지만,
    UNIQUE 제약이 있으므로 team_service 는 충돌 시 다시 뽑는다.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_reset_token() -> tuple[str, str]:
    """(원문 토큰, SHA-256 해시). DB에는 해시만 저장한다.

    - 원문: 메일 링크에 넣어 사용자에게 보낸다. 서버는 보관하지 않는다.
    - 해시: `password_reset_tokens.token_hash` (CHAR(64)) 에 저장. 사용자가 링크를 열면 받은 원문을
      다시 SHA-256 해시해 이 값으로 조회한다.
    DB 가 유출되어도 해시로는 링크를 만들 수 없다. 만료(30분)·1회 사용 제한은 호출부가
    `expires_at` / `used_at` 으로 관리한다.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()
