"""AI 설명 검증 (docs/07 FR-54) — 과거 확정 배정에 체인 A · B · C 를 돌려 결과를 docs/eval_result.md 에 쓴다.

배포된 서버를 **API 로** 부른다. 키는 서버에만 있으므로 로컬에 키를 둘 필요가 없고, 운영과 똑같은 경로(가드레일 · 캐시 ·
재시도 · 예비 모델)를 그대로 잰다.

    cd backend && uv run python -m scripts.eval_llm --base https://hooply-backend.onrender.com
    ... --events 6        # 최근 지난 회차 몇 개 (기본 10)
    ... --out ../docs/eval_result.md

표본은 데모 팀("일요 코트메이트")뿐이다. 실제 동호회 팀원의 데이터는 평가 목적으로 외부 모델에 보내지 않는다 —
그 팀 매니저·팀원이 화면을 열 때만 가명으로 나간다. 결과 파일에 표본 출처를 적는다 (명세 FR-54 수용 기준).

세는 것
  호출 수 · 새 호출/저장된 결과 · AI 결과(검증 통과) · 폴백과 사유별 건수 · 새 호출의 응답 시간(평균 · 최대)
자동 점검 (AI 결과만)
  가명(P숫자)이 남지 않았는가 · 그날 명단에 없는 이름이 없는가 · 팀원용에 등급·점수·순위가 없는가 ·
  전술 설명이 추천 순서를 지켰는가 · 필수 칸이 비지 않았는가
"""

from __future__ import annotations

import argparse
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

KST = ZoneInfo("Asia/Seoul")
DEMO_TEAM = "일요 코트메이트"
MANAGER = "manager@demo.com"
MEMBERS = [f"m{i:02d}@demo.com" for i in range(1, 21)]
PASSWORD = "demo1234"
ALIAS_LEFT = re.compile(r"(?<![A-Za-z])P\d+(?!\d)")
LEAK = re.compile(r"등급|점수|순위|실력이\s*(?:높|낮)")
PACE = 6.5  # 같은 사용자의 새 호출 사이 간격(초) — 서버의 사용자당 분당 10회 제한 아래로


@dataclass
class Call:
    chain: str
    event: str
    ok: bool  # HTTP 200
    fallback: bool
    cached: bool
    fail_reason: str | None
    seconds: float
    problems: list[str] = field(default_factory=list)
    sample: Any = None


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/") + "/api/v1"
        self.http = httpx.Client(timeout=60)
        self.tokens: dict[str, str] = {}
        self.last_call: dict[str, float] = defaultdict(float)

    def login(self, email: str) -> bool:
        r = self.http.post(f"{self.base}/auth/login", json={"email": email, "password": PASSWORD})
        if r.status_code != 200:
            return False
        self.tokens[email] = r.json()["access_token"]
        return True

    def req(self, who: str, method: str, path: str, **kw) -> httpx.Response:
        return self.http.request(method, f"{self.base}{path}", headers={"Authorization": f"Bearer {self.tokens[who]}"}, **kw)

    def ai(self, who: str, method: str, path: str, **kw) -> tuple[httpx.Response, float]:
        wait = PACE - (time.monotonic() - self.last_call[who])
        if wait > 0:
            time.sleep(wait)
        t0 = time.monotonic()
        r = self.req(who, method, path, **kw)
        took = time.monotonic() - t0
        if r.status_code == 200 and not r.json().get("cached"):
            self.last_call[who] = time.monotonic()
        return r, took


def _texts(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _texts(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _texts(v)]
    return []


def _names_ok(texts: list[str], roster: set[str], everyone: set[str]) -> list[str]:
    """팀 이름 목록(everyone) 중 그날 명단(roster)에 없는 사람이 글에 나오면 문제."""
    outsiders = everyone - roster
    return sorted({n for n in outsiders for t in texts if n in t})


def run(base: str, n_events: int) -> tuple[list[Call], dict[str, Any]]:
    c = Client(base)
    assert c.login(MANAGER), "매니저 데모 계정으로 로그인하지 못했어요"
    teams = c.req(MANAGER, "GET", "/me/teams").json()["items"]
    team = next(t for t in teams if DEMO_TEAM in str(t))
    tid = team.get("team_id") or team.get("id")
    everyone = {p["display_name"] for p in c.req(MANAGER, "GET", f"/teams/{tid}/players").json()["items"]}
    today = datetime.now(KST).date().isoformat()
    events = c.req(MANAGER, "GET", f"/teams/{tid}/events", params={"size": 50}).json()["items"]
    past = sorted((e for e in events if e["adopted_candidate_id"] and e["event_date"] < today), key=lambda e: e["event_date"])[-n_events:]

    # 팀원 계정 → 이 팀의 player_id
    member_of: dict[int, str] = {}
    for email in MEMBERS:
        if c.login(email):
            pid = c.req(email, "GET", f"/teams/{tid}").json().get("my_player_id")
            if pid:
                member_of[pid] = email

    calls: list[Call] = []
    for ev in past:
        label = ev["event_date"]
        adopted = c.req(MANAGER, "GET", f"/events/{ev['id']}/assignment/adopted").json()
        roster = {m["display_name"] for sq in adopted["squads"] for m in sq["members"]}

        # A — 매니저용
        r, took = c.ai(MANAGER, "POST", f"/assignments/candidates/{ev['adopted_candidate_id']}/ai-explanation")
        calls.append(_check_a(label, r, took, roster, everyone))

        # B — 팀마다 그 팀 팀원 한 명으로 (서버는 팀마다 한 번 부른다)
        for sq in adopted["squads"]:
            who = next((member_of[m["id"]] for m in sq["members"] if m["id"] in member_of), None)
            if who is None:
                continue
            r, took = c.ai(who, "GET", f"/events/{ev['id']}/assignment/adopted/ai-message")
            calls.append(_check_b(label, r, took, roster, everyone))

        # C — 팀마다 전술 설명 (대인 수비 보기)
        rec = c.req(MANAGER, "GET", f"/events/{ev['id']}/tactics/recommend").json()
        for sq in rec["squads"]:
            if not sq["items"]:
                continue
            r, took = c.ai(MANAGER, "POST", f"/events/{ev['id']}/tactics/ai-recommend", params={"squad_no": sq["squad_no"]})
            calls.append(_check_c(label, r, took, [it["play_key"] for it in sq["items"]], roster, everyone))

    meta = {"base": base, "team": DEMO_TEAM, "events": [e["event_date"] for e in past], "members_logged_in": len(member_of)}
    return calls, meta


def _base(chain: str, event: str, r: httpx.Response, took: float) -> Call:
    if r.status_code != 200:
        return Call(chain, event, False, True, False, f"http_{r.status_code}", took)
    b = r.json()
    return Call(chain, event, True, b["fallback"], b.get("cached", False), b.get("fail_reason"), took, sample=b)


def _common(call: Call, texts: list[str], roster: set[str], everyone: set[str]) -> None:
    if any(ALIAS_LEFT.search(t) for t in texts):
        call.problems.append("가명이 남음")
    if bad := _names_ok(texts, roster, everyone):
        call.problems.append(f"명단 밖 이름: {', '.join(bad)}")


def _check_a(event, r, took, roster, everyone) -> Call:
    call = _base("A", event, r, took)
    if call.ok and not call.fallback:
        b = call.sample
        _common(call, _texts({k: b[k] for k in ("summary", "key_players", "chemistry", "gaps", "watch_point")}), roster, everyone)
        if not b["summary"] or not (b["key_players"] or b["chemistry"]):
            call.problems.append("필수 칸이 빔")
    return call


def _check_b(event, r, took, roster, everyone) -> Call:
    call = _base("B", event, r, took)
    if call.ok and not call.fallback:
        b = call.sample
        texts = _texts({k: b[k] for k in ("why_position", "role", "partner")})
        _common(call, texts, roster, everyone)
        if any(LEAK.search(t) for t in texts):
            call.problems.append("실력 정보 누설")
        if not b["why_position"] or not b["role"]:
            call.problems.append("필수 칸이 빔")
    return call


def _check_c(event, r, took, order, roster, everyone) -> Call:
    call = _base("C", event, r, took)
    if call.ok and not call.fallback:
        b = call.sample
        _common(call, _texts({"one_liner": b["one_liner"], "items": b["items"]}), roster, everyone)
        if [it["play_key"] for it in b["items"]] != order:
            call.problems.append("추천 순서가 바뀜")
        if not any(it["key_roles"] for it in b["items"]):
            call.problems.append("핵심 자리가 모두 빔")
    return call


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------

CHAIN_NAME = {"A": "A · 매니저용 배정 설명", "B": "B · 팀원용 AI 한마디", "C": "C · 전술 추천 설명"}


def _sample_md(call: Call) -> list[str]:
    b = call.sample
    if call.chain == "A":
        lines = [f"- 요약: {b['summary']}"] + [f"- 활약: {x}" for x in b["key_players"]] + [f"- 조합: {x}" for x in b["chemistry"]]
        lines += [f"- 부족: {x}" for x in b["gaps"]] + ([f"- 주의: {b['watch_point']}"] if b["watch_point"] else [])
    elif call.chain == "B":
        lines = [f"- 왜 이 포지션: {b['why_position']}", f"- 기대 역할: {b['role']}"] + ([f"- 호흡: {b['partner']}"] if b["partner"] else [])
    else:
        lines = [f"- AI 코치: {b['one_liner']}"]
        for it in b["items"]:
            lines.append(f"- {it['play_key'].removeprefix('preset:')}: {it['reason']}")
            lines += [f"  - {k}" for k in it["key_roles"]] + ([f"  - 주의: {it['caution']}"] if it["caution"] else [])
    return lines


def report(calls: list[Call], meta: dict[str, Any]) -> str:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    out = [
        "# AI 설명 검증 결과 (docs/07 FR-54)",
        "",
        f"- 실행: {now} · 대상 서버: `{meta['base']}` · 스크립트: `backend/scripts/eval_llm.py`",
        (f"- **표본 출처: 데모 팀 \"{meta['team']}\" 지난 확정 배정 {len(meta['events'])}건 ({', '.join(meta['events'])}) · 실제 동호회 팀 0건** — "
         "실제 팀원 데이터는 평가 목적으로 외부 모델에 보내지 않는다"),
        (f"- 호출 합계 {len(calls)}건 (A {sum(c.chain == 'A' for c in calls)} · B {sum(c.chain == 'B' for c in calls)} · C {sum(c.chain == 'C' for c in calls)}). "
         "B 는 팀마다 팀원 한 명으로, C 는 팀마다 대인 수비 보기로 부른다"),
        "- \"저장된 결과\"는 앞서 같은 입력으로 실제로 부른 결과를 다시 쓴 것이다 (응답 시간은 새 호출만 센다)",
        "",
        "## 체인별 요약",
        "",
        "| 체인 | 호출 | 새 호출 / 저장된 결과 | AI 결과(검증 통과) | 폴백 | 폴백 사유 | 새 호출 응답 시간 평균 · 최대 | 자동 점검 문제 |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for ch in "ABC":
        cs = [c for c in calls if c.chain == ch]
        if not cs:
            continue
        fresh = [c.seconds for c in cs if not c.cached and c.ok]
        reasons = Counter(c.fail_reason or "?" for c in cs if c.fallback)
        t = f"{statistics.mean(fresh):.1f}초 · {max(fresh):.1f}초" if fresh else "—"
        out.append(
            f"| {CHAIN_NAME[ch]} | {len(cs)} | {sum(not c.cached for c in cs)} / {sum(c.cached for c in cs)} | "
            f"{sum(not c.fallback for c in cs)} | {sum(c.fallback for c in cs)} | "
            f"{', '.join(f'{k} {v}' for k, v in reasons.items()) or '—'} | {t} | {sum(bool(c.problems) for c in cs)} |"
        )
    problems = [c for c in calls if c.problems]
    out += ["", "## 자동 점검", ""]
    out += [("- 가명이 남지 않았는가 · 그날 명단에 없는 사람을 말하지 않았는가 · 팀원용에 등급·점수·순위가 없는가 · "
             "전술 설명이 추천 순서를 지켰는가 · 필수 칸이 비지 않았는가 (AI 결과만 점검)"), ""]
    out += [f"- {c.event} {c.chain}: {', '.join(c.problems)}" for c in problems] or ["- 문제 없음"]
    out += ["", "## 예시 (체인별 첫 AI 결과)", ""]
    for ch in "ABC":
        first = next((c for c in calls if c.chain == ch and not c.fallback), None)
        if first:
            out += [f"### {CHAIN_NAME[ch]} — {first.event}", "", *_sample_md(first), ""]
    out += ["## 해석과 한계", "",
            ("- 판단(활약 · 조합 · 부족한 역할 · 포지션 이유 · 추천 전술과 자리)은 서버 규칙이 하고 AI 는 문장만 쓰므로, "
             "이 평가는 **문장이 규칙의 판단을 벗어나지 않는가**를 본다. 판단 자체의 정확도는 실제 배정이 쌓인 뒤 따로 본다 (명세 O4)."),
            "- 폴백은 오류가 아니다 — 가드레일이 걸러냈거나 공급자가 붐빌 때 기존 규칙 설명을 보여 준 것이다.",
            "- 무료 등급 Gemini 라 응답 시간과 과부하(503)는 시간대에 따라 달라진다.", ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="https://hooply-backend.onrender.com")
    ap.add_argument("--events", type=int, default=10)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "eval_result.md"))
    args = ap.parse_args()
    calls, meta = run(args.base, args.events)
    Path(args.out).write_text(report(calls, meta), encoding="utf-8")
    print(f"{args.out} 에 썼어요 — 호출 {len(calls)}건, 폴백 {sum(c.fallback for c in calls)}건, 점검 문제 {sum(bool(c.problems) for c in calls)}건")


if __name__ == "__main__":
    main()
