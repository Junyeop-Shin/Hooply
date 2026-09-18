"""요청 횟수 제한 — 로그인·가입·비밀번호 찾기처럼 대입 공격의 표적이 되는 경로에만 건다 (7.4절 429 RATE_LIMITED).

메모리 안의 슬라이딩 윈도우다. 서버가 한 대(Render 단일 인스턴스)라는 전제이며, 여러 대로 늘리면
Redis 같은 공유 저장소로 바꿔야 한다. 재시작하면 카운터가 비지만, 그 사이 공격을 늦추는 목적에는 충분하다.

키는 두 겹이다: 요청 IP 와 (있으면) 이메일. IP 만 보면 공용 와이파이의 다른 사람이 막히고,
이메일만 보면 공격자가 계정을 바꿔 가며 계속 시도할 수 있어서 둘 다 센다.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core import errors

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def check(key: str, limit: int, window_seconds: int) -> None:
    """`window_seconds` 안에 `key` 로 `limit` 번을 넘기면 429. 넘지 않으면 이번 요청을 기록한다."""
    from app.core.config import get_settings

    if not get_settings().rate_limit_enabled:
        return
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise errors.RateLimited()
        q.append(now)


def reset() -> None:
    """테스트용 — 카운터를 모두 비운다."""
    with _lock:
        _hits.clear()


def client_ip(request: Request) -> str:
    """프록시(Render) 뒤에서는 X-Forwarded-For 의 첫 값이 실제 클라이언트다."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
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
PASSWORD = Limit("password", 5, 60)  # 재설정 메일 요청 · 재설정 토큰 시도
