"""요청 횟수 제한 — 로그인·가입·비밀번호 찾기처럼 대입 공격의 표적이 되는 경로에만 건다 (7.4절 429 RATE_LIMITED).

메모리 안의 슬라이딩 윈도우다. 서버가 한 대(Render 단일 인스턴스)라는 전제이며, 여러 대로 늘리면
Redis 같은 공유 저장소로 바꿔야 한다. 재시작하면 카운터가 비지만, 그 사이 공격을 늦추는 목적에는 충분하다.

키는 두 겹이다: 요청 IP 와 (있으면) 이메일. IP 만 보면 공용 와이파이의 다른 사람이 막히고,
이메일만 보면 공격자가 계정을 바꿔 가며 계속 시도할 수 있어서 둘 다 센다.
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
MAX_KEYS = 20_000  # 이보다 많아지면 창이 지난 키를 훑어 지우고, 그래도 넘치면 오래된 키부터 버린다
SWEEP_INTERVAL = 300.0  # 초. 이 간격마다 한 번 전체를 훑는다
_last_sweep = 0.0


def _prune(q: deque[float], window: int, now: float) -> None:
    while q and now - q[0] > window:
        q.popleft()


def _sweep(now: float) -> None:
    """창이 지난 키를 지운다. 그래도 MAX_KEYS 를 넘으면 마지막 요청이 오래된 키부터 버린다. `_lock` 안에서 부른다."""
    global _last_sweep
    _last_sweep = now
    for key in list(_hits):
        window, q = _hits[key]
        _prune(q, window, now)
        if not q:
            del _hits[key]
    if len(_hits) > MAX_KEYS:
        for key, _ in sorted(_hits.items(), key=lambda kv: kv[1][1][-1])[: len(_hits) - MAX_KEYS]:
            del _hits[key]


def check(key: str, limit: int, window_seconds: int) -> None:
    """`window_seconds` 안에 `key` 로 `limit` 번을 넘기면 429. 넘지 않으면 이번 요청을 기록한다."""
    from app.core.config import get_settings

    if not get_settings().rate_limit_enabled:
        return
    now = time.monotonic()
    with _lock:
        if now - _last_sweep > SWEEP_INTERVAL or len(_hits) > MAX_KEYS:
            _sweep(now)
        entry = _hits.get(key)
        if entry is None:
            entry = _hits[key] = (window_seconds, deque())
        q = entry[1]
        _prune(q, window_seconds, now)
        if len(q) >= limit:
            raise errors.RateLimited()
        q.append(now)


def reset() -> None:
    """테스트용 — 카운터를 모두 비운다."""
    with _lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    """요청한 사람의 IP.

    운영은 Cloudflare 뒤에 있다 (응답에 server: cloudflare · cf-ray). Cloudflare 는 `CF-Connecting-IP`(엔터프라이즈는
    `True-Client-IP`)를 자기가 본 접속 IP 로 **덮어써서** 넘기므로 이 값은 클라이언트가 꾸밀 수 없다. 반면
    X-Forwarded-For 의 첫 값은 클라이언트가 보낸 헤더가 그대로 앞에 남아 있어, 그걸 믿으면 헤더만 바꿔 가며
    제한을 피할 수 있었다. 둘 다 없으면(로컬 · 테스트) 소켓 주소.
    """
    for header in ("cf-connecting-ip", "true-client-ip"):
        v = request.headers.get(header)
        if v and v.strip():
            return v.strip()
    return request.client.host if request.client else "unknown"


class Limit:
    """엔드포인트에 붙이는 의존성. `Depends(Limit("login", 10, 60))` 처럼 쓴다.

    본문의 이메일까지 키에 넣고 싶은 경로는 라우터에서 `by_email()` 을 한 번 더 부른다
    (본문은 Pydantic 이 파싱한 뒤에야 알 수 있어 의존성 단계에서는 IP 만 센다).
    """

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name, self.limit, self.window = name, limit, window_seconds

    def __call__(self, request: Request) -> None:
        check(f"{self.name}:ip:{client_ip(request)}", self.limit, self.window)

    def by_email(self, email: str) -> None:
        check(f"{self.name}:email:{email.strip().lower()}", self.limit, self.window)


# 분당 IP 기준. 사람이 손으로 틀리는 속도보다 넉넉하고, 자동 대입에는 턱없이 부족한 수
LOGIN = Limit("login", 10, 60)
SIGNUP = Limit("signup", 5, 60)
ADMIN_LOGIN = Limit("admin-login", 10, 60)  # 관리자 콘솔(/admin) 로그인 폼
PASSWORD = Limit("password", 5, 60)  # 재설정 메일 요청 · 재설정 토큰 시도 (메일 요청은 이메일로도 센다)
