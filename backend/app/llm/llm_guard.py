"""LLM 공통 가드레일 (docs/07 FR-48 ~ FR-50, 9절). 모든 체인 호출은 `run()` 을 거친다.

    캐시 확인 → (모델 없음이면 폴백) → 사용자당 횟수 제한 → 호출(타임아웃) → 출력 검증 → 실명 복원 → 캐시 저장

판단은 규칙과 알고리즘이 하고 LLM 은 문장만 쓴다. 그래서 LLM 이 입력에 없는 사람·숫자·전술을 말하면 버린다.

검증 규칙 (명세 9절)
  1. 가명: 선수는 P1…Pn, 팀은 A·B(3팀이면 D 까지 — C 는 센터 포지션과 겹쳐 쓰지 않는다). 실명은 입력 어디에도 넣지 않는다 (`Aliases`)
  2. 복원: `P(\\d+)(?!\\d)` 로 숫자를 통째로 읽어 P1 과 P10 이 섞이거나 "P3가" 처럼 조사가 붙어도 정확히 바꾼다
  3. 가명 검사: 출력의 P숫자가 입력에 없으면 전체 폐기 (unknown_alias). 체인별 추가 검사(C 의 전술 id)도 같은 사유
  4. 숫자 검사: 출력 숫자가 입력에 없으면 **그 문장만** 버린다 (unknown_number). 농구 용어(3점 · 1번~5번 · 2-3 …)는 허용,
     0.3 · 0.30 · 30% 는 같은 값. 쓸 만한 내용이 남지 않으면 폴백
  5. 누설 검사(B): 등급 · 점수 · 순위 · "실력이 높/낮" 이 있으면 전체 폐기 (leak)
  6. 형식: `with_structured_output` 결과가 스키마를 어기면 폐기 (schema). 글자 수 상한을 넘으면 자른다
  7. 폴백: 체인이 넘긴 규칙 문장. 화면에서는 "AI 설명" 표시 없이 보여 준다
  8. 기록: llm_results 에 체인 · 성공/폴백 · 사유 · 지연 · 모델. 입력 원문은 저장하지 않는다. 로그에도 이름을 남기지 않는다
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.josa import (  # noqa: F401 — josa 는 테스트·다른 모듈이 여기서 가져간다
    josa,
    substitute,
)
from app.llm import model as llm_model
from app.models import LlmResult

log = logging.getLogger("hooply.llm")

ALIAS_RE = re.compile(r"P(\d+)(?!\d)")
SQUAD_ALIASES = "ABD"  # 팀 가명 — C 는 포지션 C(센터)와 겹쳐 복원할 때 "C 자리" 가 팀 이름으로 바뀌므로 건너뛴다
SQUAD_RE = re.compile(rf"(?<![A-Za-z0-9])([{SQUAD_ALIASES}])(?![A-Za-z0-9])")
# 숫자 검사에서 빼는 농구 용어. 긴 것부터 (1-3-1 을 1-3 과 1 로 쪼개지 않게)
TERM_RE = re.compile(r"1-3-1|2-3|3-2|1:1|2:2|[23]점|[1-5]번")
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
LEAK_RE = re.compile(r"등급|점수|순위|실력이\s*(?:높|낮)")
SENTENCE_RE = re.compile(r"(?<=[.!?。])\s+|\n+")
RETRY_AFTER = timedelta(minutes=10)  # 폴백으로 끝난 결과는 이만큼 지나면 다시 시도한다
TRANSIENT_RETRY_AFTER = timedelta(minutes=1)  # 공급자 과부하·타임아웃처럼 곧 풀리는 실패는 더 빨리
RETRY_WAIT = 1.5  # 일시적 오류면 한 번 더 부르기 전에 쉬는 시간 (초)
MAX_CHARS = 300  # 문자열 하나의 기본 상한 (체인이 바꿀 수 있다)

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm")


# ---------------------------------------------------------------------------
# 가명
# ---------------------------------------------------------------------------


class Aliases:
    """선수 → P1…Pn, 팀 → A·B·D. 넣은 순서대로 번호를 매기므로 호출하는 쪽이 팀·배정 순서로 넣으면 번호가 고정된다."""

    def __init__(self) -> None:
        self._by_player: dict[int, str] = {}
        self._name: dict[str, str] = {}  # 가명 → 실명
        self._by_squad: dict[int, str] = {}

    def player(self, player_id: int, name: str) -> str:
        if player_id not in self._by_player:
            alias = f"P{len(self._by_player) + 1}"
            self._by_player[player_id] = alias
            self._name[alias] = name
        return self._by_player[player_id]

    def squad(self, squad_no: int, name: str) -> str:
        if squad_no not in self._by_squad:
            alias = SQUAD_ALIASES[len(self._by_squad)] if len(self._by_squad) < len(SQUAD_ALIASES) else f"T{len(self._by_squad) + 1}"
            self._by_squad[squad_no] = alias
            self._name[alias] = name
        return self._by_squad[squad_no]

    @property
    def players(self) -> set[str]:
        return set(self._by_player.values())

    def of(self, player_id: int) -> str | None:
        return self._by_player.get(player_id)

    def restore(self, text: str) -> str:
        """가명 → 실명. 바로 뒤 조사는 실명의 받침에 맞춘다 ("P3가" → "서장훈이", "A와" → "블랙과")."""
        text = substitute(text, r"(P\d+)(?!\d)", self._name.get)
        return substitute(text, SQUAD_RE.pattern, self._name.get)

    def player_id_of(self, alias: str) -> int | None:
        return next((pid for pid, a in self._by_player.items() if a == alias), None)


# ---------------------------------------------------------------------------
# 검사 도구
# ---------------------------------------------------------------------------


def _strings(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list | tuple):
        return [s for v in obj for s in _strings(v)]
    return []


def _map_strings(obj: Any, fn: Callable[[str], str | None]) -> Any:
    """문자열마다 fn 을 적용한다. None 이면 목록에서는 빼고, 필드에서는 빈 문자열로 둔다."""
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            r = _map_strings(v, fn)
            out[k] = "" if r is None and isinstance(v, str) else r
        return out
    if isinstance(obj, list):
        return [r for r in (_map_strings(v, fn) for v in obj) if r is not None]
    return obj


def unknown_aliases(output: Any, allowed: set[str]) -> set[str]:
    return {m.group(0) for s in _strings(output) for m in ALIAS_RE.finditer(s)} - allowed


def input_numbers(payload: Any) -> set[float]:
    """입력에 나온 모든 숫자 (값 그대로 + 문자열 안의 숫자). 가명 번호는 숫자로 치지 않는다."""
    out: set[float] = set()

    def walk(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, int | float | Decimal):
            out.add(float(v))
        elif isinstance(v, str):
            for m in NUM_RE.finditer(ALIAS_RE.sub(" ", v)):
                out.add(float(m.group(0).rstrip("%")))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list | tuple):
            for x in v:
                walk(x)

    walk(payload)
    return out


def _number_ok(token: str, allowed: set[float]) -> bool:
    """0.3 · 0.30 · 30% 를 같은 값으로 본다. 출력이 쓴 자릿수로 반올림한 값도 인정 (입력 0.337 → 출력 0.34 · 34%)."""
    pct = token.endswith("%")
    raw = token.rstrip("%")
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    x = float(raw)
    # (비교할 값, 그 값의 자릿수). 30% 는 0.30, 0.3 은 30(%) 으로도 본다
    cands = [(x, decimals), (x / 100, decimals + 2)] if pct else [(x, decimals), (x * 100, max(decimals - 2, 0))]
    return any(round(a, d) == round(c, d) for a in allowed for c, d in cands)


def filter_numbers(text: str, allowed: set[float]) -> str | None:
    """입력에 없는 숫자가 든 문장을 뺀다. 남는 문장이 없으면 None."""
    kept = []
    for sent in SENTENCE_RE.split(text.strip()):
        if not sent:
            continue
        probe = TERM_RE.sub(" ", ALIAS_RE.sub(" ", sent))
        if all(_number_ok(m.group(0), allowed) for m in NUM_RE.finditer(probe)):
            kept.append(sent)
    return " ".join(kept) if kept else None


def has_leak(output: Any) -> bool:
    return any(LEAK_RE.search(s) for s in _strings(output))


def cache_key(chain: str, parts: dict[str, Any]) -> str:
    raw = json.dumps({"chain": chain, **parts}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------


@dataclass
class ChainCall:
    """체인 하나를 부르는 데 필요한 것. 입력(`payload`·`messages`)은 이미 가명으로 바꾼 상태여야 한다."""

    chain: str  # A · B · C
    schema: type[BaseModel]
    messages: list[tuple[str, str]]  # [("system", …), ("human", …)]
    payload: dict[str, Any]  # 숫자 검사의 기준이 되는 입력
    aliases: Aliases
    fallback: dict[str, Any]  # 폴백 결과 (이미 실명)
    key_parts: dict[str, Any]  # 캐시 키 재료 (명세 FR-49)
    leak_check: bool = False  # B 만
    usable: Callable[[dict[str, Any]], bool] = lambda out: bool(_strings(out))  # 숫자 검사 뒤 쓸 만한 게 남았나
    extra_check: Callable[[dict[str, Any]], bool] | None = None  # False 면 unknown_alias (C: 전술 id)
    max_chars: int = MAX_CHARS
    # 실명 복원 **전에** 체인별로 다듬기 (가명을 player_id 로 바꾸는 등). 여기서 만든 숫자는 복원·검사 대상이 아니다
    post: Callable[[dict[str, Any]], dict[str, Any]] | None = None


@dataclass
class GuardOutcome:
    output: dict[str, Any]
    fallback: bool
    cached: bool = False
    fail_reason: str | None = None
    latency_ms: int | None = None


def _validate(call: ChainCall, raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """(실명으로 되돌린 결과, 실패 사유)."""
    try:
        data = raw.model_dump() if isinstance(raw, BaseModel) else call.schema.model_validate(raw).model_dump()
    except (ValidationError, TypeError, ValueError):
        return None, "schema"
    if unknown_aliases(data, call.aliases.players):
        return None, "unknown_alias"
    if call.extra_check is not None and not call.extra_check(data):
        return None, "unknown_alias"
    if call.leak_check and has_leak(data):
        return None, "leak"
    allowed = input_numbers(call.payload)
    data = _map_strings(data, lambda s: filter_numbers(s, allowed))
    if not call.usable(data):
        return None, "unknown_number"
    data = _map_strings(data, lambda s: s[: call.max_chars])
    if call.post is not None:
        data = call.post(data)
    data = _map_strings(data, call.aliases.restore)
    return data, None


def is_transient(reason: str | None) -> bool:
    """곧 풀릴 수 있는 실패 — 타임아웃, 공급자 과부하(503)·한도(429)·서버 오류(500)."""
    return bool(reason) and (reason == "timeout" or any(reason.endswith(f":{c}") for c in (429, 500, 503)))


def _error_reason(e: Exception) -> str:
    """공급자 오류 → "error:<예외 이름>:<HTTP 상태>" (llm_results.fail_reason 40자). 모델 이름 오류(404) · 키 오류(400/403) · 한도(429)를 가른다."""
    code = next((getattr(e, a) for a in ("status_code", "code", "status") if isinstance(getattr(e, a, None), int)), None)
    return (f"error:{type(e).__name__}" + (f":{code}" if code else ""))[:40]


def _store(db: Session, call: ChainCall, key: str, out: GuardOutcome, model: str) -> None:
    values = {
        "chain": call.chain, "cache_key": key, "output": out.output, "fallback": out.fallback,
        "fail_reason": out.fail_reason, "latency_ms": out.latency_ms, "model": model[:60],
        "created_at": datetime.now(UTC),
    }
    stmt = insert(LlmResult).values(**values)
    stmt = stmt.on_conflict_do_update(index_elements=["cache_key"], set_={k: stmt.excluded[k] for k in values if k != "cache_key"})
    db.execute(stmt)
    db.commit()


def run(db: Session, call: ChainCall, *, user_id: int | None) -> GuardOutcome:
    key = cache_key(call.chain, call.key_parts)
    row = db.scalar(select(LlmResult).where(LlmResult.cache_key == key))
    window = TRANSIENT_RETRY_AFTER if row is not None and is_transient(row.fail_reason) else RETRY_AFTER
    if row is not None and (not row.fallback or datetime.now(UTC) - row.created_at < window):
        output = {k: v for k, v in row.output.items() if k != "_error"}
        return GuardOutcome(output=output, fallback=row.fallback, cached=True, fail_reason=row.fail_reason)

    runner = llm_model.structured(call.schema)
    if runner is None:  # 키 없음 · 꺼짐 — 기록하지 않는다 (키를 넣으면 바로 부르도록)
        return GuardOutcome(output=call.fallback, fallback=True, fail_reason="disabled")

    ratelimit.check(f"llm:user:{user_id}", get_settings().llm_rate_per_minute, 60)  # 넘으면 429 RATE_LIMITED
    t0 = time.monotonic()
    deadline = t0 + get_settings().llm_timeout_seconds
    reason: str | None = None
    detail: str | None = None
    data: dict[str, Any] | None = None
    used_model = llm_model.model_name()
    for attempt in range(2):  # 일시적 오류면 남은 시간 안에서 한 번 더 (두 번째는 예비 모델)
        try:
            raw = _pool.submit(runner.invoke, call.messages).result(timeout=max(deadline - time.monotonic(), 0.01))
            if isinstance(raw, dict) and "parsed" in raw:  # include_raw=True 응답
                meta = getattr(raw.get("raw"), "response_metadata", None) or {}
                version = meta.get("model_version") or meta.get("model_name")  # Gemini 는 model_name 에 실제 버전을 담는다
                used_model = version or used_model
                if raw.get("parsing_error") is not None or raw.get("parsed") is None:
                    reason = "schema"
                    break
                raw = raw["parsed"]
            data, reason = _validate(call, raw)
            detail = None
            break
        except FutureTimeout:
            reason = "timeout"
            break
        except Exception as e:  # noqa: BLE001 — 공급자 오류는 모두 폴백
            reason = "schema" if type(e).__name__ == "OutputParserException" else _error_reason(e)
            detail = str(e)[:300]
            # 보낸 입력은 가명뿐이라 공급자 오류 문구에 실명이 섞이지 않는다. 원인(모델 이름·키·한도)을 알 수 있게 앞부분을 남긴다
            log.warning("llm chain=%s attempt=%d error=%s %s", call.chain, attempt + 1, type(e).__name__, detail)
            if attempt == 0 and is_transient(reason) and deadline - time.monotonic() > RETRY_WAIT + 2:
                time.sleep(RETRY_WAIT)
                runner = llm_model.structured(call.schema, fallback=True) or runner
                used_model = llm_model.model_name(fallback=True)
                continue
            break
    latency = int((time.monotonic() - t0) * 1000)
    out = (
        GuardOutcome(output=data, fallback=False, latency_ms=latency)
        if data is not None
        else GuardOutcome(output=call.fallback, fallback=True, fail_reason=reason, latency_ms=latency)
    )
    stored = out if detail is None else GuardOutcome(
        output={**out.output, "_error": detail}, fallback=True, fail_reason=reason, latency_ms=latency,
    )  # 공급자 오류 문구는 DB 에만 (원인 확인용). 응답에는 싣지 않는다
    log.info("llm chain=%s fallback=%s reason=%s latency_ms=%d", call.chain, out.fallback, out.fail_reason, latency)
    _store(db, call, key, stored, used_model)
    return out
