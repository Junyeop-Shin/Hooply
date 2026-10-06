"""요청 횟수 제한 — 로그인·가입·비밀번호 찾기처럼 대입 공격의 표적이 되는 경로에만 건다 (7.4절 429 RATE_LIMITED).

메모리 안의 슬라이딩 윈도우다. 서버가 한 대(Render 단일 인스턴스)라는 전제이며, 여러 대로 늘리면
Redis 같은 공유 저장소로 바꿔야 한다. 재시작하면 카운터가 비지만, 그 사이 공격을 늦추는 목적에는 충분하다.

지금 걸려 있는 규칙
  - 로그인        IP 당 분당 10회 (시도 전부) + (IP, 이메일) 쌍마다 10분에 **실패** 10회. 성공하면 그 쌍의 실패 기록을 비운다
  - 관리자 콘솔   로그인과 같은 두 겹 (admin-login)
  - 가입          IP 당 분당 5회 (이메일로는 세지 않는다 — 같은 이메일은 어차피 409 EMAIL_DUPLICATED)
  - 비밀번호 찾기 IP 당 분당 5회. 이메일마다는 한 시간에 메일 5통 — 넘으면 **조용히** 보내지 않고 202 (429 가 아니다)
  - 비밀번호 재설정 IP 당 분당 5회
  - AI 호출 · 전술 댓글 사용자당 분당 10회 (llm_guard · team_play_service 가 `check` 를 직접 부른다)

왜 이메일로 "시도 전부" 를 세지 않는가: 그렇게 하면 공격자가 남의 이메일로 틀린 비밀번호를 열 번 보내는 것만으로
그 사람을 어느 IP 에서도 못 들어오게 잠글 수 있었다 (계정 잠금 DoS). 그래서 이메일 축은 (IP, 이메일) 쌍의 실패
횟수로만 세고, 성공하면 지운다 — 같은 IP 에서 한 계정을 두드리는 대입은 막히고, 피해자는 자기 IP 에서 그대로 들어온다.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request

from app.core import errors

_lock = threading.Lock()
# 키 → (창 길이, 최근 요청 시각들). 창이 비면 키를 지운다 — 한 번 오고 마는 IP 들로 메모리가 계속 늘지 않게
_hits: dict[str, tuple[int, deque[float]]] = {}
MAX_KEYS = 20_000  # 이보다 많아지면 창이 지난 키를 훑어 지우고, 그래도 넘치면 오래된 키부터 버려 90% 까지 줄인다
TRIM_RATIO = 0.9  # 넘쳤을 때 남기는 비율 — 한 개 넘을 때마다 매번 훑지 않게 여유를 둔다
SWEEP_INTERVAL = 300.0  # 초. 이 간격마다 한 번 전체를 훑는다
MIN_SWEEP_INTERVAL = 1.0  # 초. 키가 넘쳐도 이보다 자주는 훑지 않는다 (요청마다 전체를 훑는 비용 방지)
_last_sweep = 0.0


def _prune(q: deque[float], window: int, now: float) -> None:
    while q and now - q[0] > window:
        q.popleft()


def _sweep(now: float) -> None:
    """창이 지난 키를 지운다. 그래도 MAX_KEYS 를 넘으면 마지막 요청이 오래된 키부터 버려 MAX_KEYS 의 90% 로 줄인다. `_lock` 안에서 부른다."""
    global _last_sweep
    _last_sweep = now
    for key in list(_hits):
        window, q = _hits[key]
        _prune(q, window, now)
        if not q:
            del _hits[key]
    if len(_hits) > MAX_KEYS:
        keep = int(MAX_KEYS * TRIM_RATIO)
        for key, _ in sorted(_hits.items(), key=lambda kv: kv[1][1][-1])[: len(_hits) - keep]:
            del _hits[key]


def _maybe_sweep(now: float) -> None:
    """`_lock` 안에서. 주기가 됐거나 키가 넘쳤을 때 훑되, 1초에 한 번을 넘지 않는다."""
    if now - _last_sweep >= MIN_SWEEP_INTERVAL and (now - _last_sweep > SWEEP_INTERVAL or len(_hits) > MAX_KEYS):
        _sweep(now)


def _enabled() -> bool:
    from app.core.config import get_settings

    return get_settings().rate_limit_enabled


def _bucket(key: str, window_seconds: int, now: float) -> deque[float]:
    entry = _hits.get(key)
    if entry is None:
        entry = _hits[key] = (window_seconds, deque())
    q = entry[1]
    _prune(q, window_seconds, now)
    return q


def check(key: str, limit: int, window_seconds: int, *, record: bool = True) -> None:
    """`window_seconds` 안에 `key` 로 `limit` 번을 넘기면 429. 넘지 않으면 이번 요청을 기록한다 (`record=False` 면 보기만)."""
    if not _enabled():
        return
    now = time.monotonic()
    with _lock:
        _maybe_sweep(now)
        q = _bucket(key, window_seconds, now)
        if len(q) >= limit:
            raise errors.RateLimited()
        if record:
            q.append(now)


def allow(key: str, limit: int, window_seconds: int) -> bool:
    """`check` 와 같되 429 를 던지지 않고 False 를 돌려준다 — 조용히 건너뛰는 상한(비밀번호 찾기 메일)에 쓴다."""
    try:
        check(key, limit, window_seconds)
    except errors.RateLimited:
        return False
    return True


def record(key: str, limit: int, window_seconds: int) -> None:
    """상한과 무관하게 한 번을 기록한다 — 실패한 뒤에 세는 경로(로그인 실패)에 쓴다."""
    if not _enabled():
        return
    now = time.monotonic()
    with _lock:
        _maybe_sweep(now)
        _bucket(key, window_seconds, now).append(now)


def clear(key: str) -> None:
    """키 하나를 비운다 (로그인 성공 → 그 (IP, 이메일) 쌍의 실패 기록 초기화)."""
    with _lock:
        _hits.pop(key, None)


def reset() -> None:
    """테스트용 — 카운터를 모두 비운다."""
    with _lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    """요청한 사람의 IP.

    운영은 Cloudflare 뒤에 있다 (응답에 server: cloudflare · cf-ray). Cloudflare 는 `CF-Connecting-IP`(엔터프라이즈는
    `True-Client-IP`)를 자기가 본 접속 IP 로 **덮어써서** 넘기므로 그 뒤에서는 이 값을 믿을 수 있다. 하지만 프록시
    없이 바로 받는 환경(로컬 · 테스트 · 다른 호스팅)에서는 누구나 그 헤더를 적어 보낼 수 있으므로, 운영 같은 환경
    (`Settings.is_production_like`)에서만 `Settings.trusted_proxy_header` 를 본다.

    그 밖에는 X-Forwarded-For 의 **마지막** 값 — 바로 앞 프록시(nginx 등)가 자기가 본 접속 주소를 끝에 덧붙이므로
    마지막 값만 믿을 수 있다. 첫 값은 클라이언트가 보낸 헤더가 그대로 남아 있어 헤더만 바꿔 가며 제한을 피할 수 있었다.
    헤더가 없으면 소켓 주소.
    """
    from app.core.config import get_settings

    s = get_settings()
    header = s.trusted_proxy_header.strip().lower()
    if header and s.is_production_like:
        v = request.headers.get(header)
        if v and v.strip():
            return v.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.strip():
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class Limit:
    """엔드포인트에 붙이는 IP 기준 의존성. `Depends(Limit("login", 10, 60))` 처럼 쓴다."""

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name, self.limit, self.window = name, limit, window_seconds

    def __call__(self, request: Request) -> None:
        check(f"{self.name}:ip:{client_ip(request)}", self.limit, self.window)

    def allow_email(self, email: str) -> bool:
        """이메일마다 조용한 상한 — 넘으면 False (429 가 아니다). 비밀번호 찾기 메일 발송에 쓴다."""
        return allow(f"{self.name}:email:{email.strip().lower()}", self.limit, self.window)


class FailureLimit:
    """(IP, 이메일) 쌍마다 **실패** 횟수를 세는 제한 — 로그인 대입 방어.

    `guard()` 를 시도 전에 불러 이미 실패가 상한에 닿았으면 429, `failed()` 를 자격 검증 실패 뒤에 불러 한 번 세고,
    `succeeded()` 를 성공 뒤에 불러 그 쌍을 비운다. 키에 IP 가 들어가므로 한 IP 의 공격이 다른 IP 의 본인을 잠그지 못한다.
    """

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name, self.limit, self.window = name, limit, window_seconds

    def key(self, request: Request, email: str) -> str:
        return f"{self.name}:fail:{client_ip(request)}:{email.strip().lower()}"

    def guard(self, request: Request, email: str) -> None:
        check(self.key(request, email), self.limit, self.window, record=False)

    def failed(self, request: Request, email: str) -> None:
        record(self.key(request, email), self.limit, self.window)

    def succeeded(self, request: Request, email: str) -> None:
        clear(self.key(request, email))


# 분당 IP 기준. 사람이 손으로 틀리는 속도보다 넉넉하고, 자동 대입에는 턱없이 부족한 수
LOGIN = Limit("login", 10, 60)
LOGIN_FAIL = FailureLimit("login", 10, 600)  # 같은 IP 에서 같은 이메일로 10분에 실패 10회
SIGNUP = Limit("signup", 5, 60)
ADMIN_LOGIN = Limit("admin-login", 10, 60)  # 관리자 콘솔(/admin) 로그인 폼
ADMIN_LOGIN_FAIL = FailureLimit("admin-login", 10, 600)
PASSWORD = Limit("password", 5, 60)  # 재설정 메일 요청 · 재설정 토큰 시도 (IP)
FORGOT_MAIL = Limit("forgot-mail", 5, 3600)  # 이메일마다 한 시간에 메일 5통 — 넘으면 조용히 보내지 않는다 (allow_email)
