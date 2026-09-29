"""AI 배정 설명 (docs/07 F19, FR-51). 입력을 DB 에서 모아 가명으로 바꾸고 llm_guard 로 부른다.

  체인 A (매니저용)  후보안 하나의 배정 근거 — 요약 · 수치 근거 2~3개 · 경기 중 확인할 점
  체인 B (팀원용)    확정 배정의 팀마다 **한 번** 불러 그 팀 선수 전원의 안내를 한꺼번에 받는다 (T13: 16명이 열어도 2회)

B 입력에는 실력 값이 없다(NFR-04). 포지션 · 팀 특징 태그 · 서로 "또 같이 뛰고 싶다" 고 고른 동료만 보낸다.
실패하면 지금의 규칙 설명 문장(A: candidate.explanation, B: metrics.player_explanation)을 그대로 보여 준다.
"""

from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import errors
from app.llm import llm_guard
from app.llm.prompts import PROMPT_VERSION, SYSTEM_A, SYSTEM_B, ExplainA, TeamMessagesB
from app.models import AssignmentCandidate, ChemistryScore, Event, Player, User
from app.models.enums import PlayerKind, Position
from app.schemas.ai import AiExplanation, AiMessage
from app.services.assignment_service import (
    STRATEGY_LABEL,
    _players_of,
    adopted_candidate,
    constraints_of,
)

GUARDS = {Position.PG, Position.SG}
BIGS = {Position.PF, Position.C}
TALL_CM = 180


def _pos(value: Any) -> str | None:
    return value.value if isinstance(value, Position) else value


def _height(p: Player) -> int | None:
    return p.height_cm if p.user is None else p.user.height_cm


def _roster(cand: AssignmentCandidate) -> list[tuple[int, list[tuple[int, str | None]]]]:
    """[(squad_no, [(player_id, 배정 포지션)…])…] — 팀 번호 · player_id 순서로 고정 (가명 번호와 캐시 키가 매번 같게)."""
    return [
        (sq.squad_no, sorted((s.player_id, _pos(s.assigned_position)) for s in sq.slots))
        for sq in sorted(cand.squads, key=lambda s: s.squad_no)
    ]


def _mutual_pairs(db: Session, ids: list[int]) -> set[tuple[int, int]]:
    rows = db.execute(
        select(ChemistryScore.player_a_id, ChemistryScore.player_b_id).where(
            ChemistryScore.pref_mutual.is_(True), ChemistryScore.player_a_id.in_(ids), ChemistryScore.player_b_id.in_(ids),
        )
    ).all()
    return {(a, b) for a, b in rows}


def _aliases(roster, players: dict[int, Player], names: dict[int, str]) -> llm_guard.Aliases:
    al = llm_guard.Aliases()
    for no, members in roster:
        al.squad(no, names[no])
        for pid, _ in members:
            al.player(pid, players[pid].display_name)
    return al


# ---------------------------------------------------------------------------
# 체인 A — 매니저용
# ---------------------------------------------------------------------------


def explain_candidate(db: Session, cand: AssignmentCandidate, user: User) -> AiExplanation:
    roster = _roster(cand)
    ids = [pid for _, ms in roster for pid, _ in ms]
    players = _players_of(db, ids)
    names = {sq.squad_no: sq.squad_name for sq in cand.squads}
    al = _aliases(roster, players, names)
    m = cand.metrics or {}
    avg = m.get("squad_avg_skill") or []
    coverage = m.get("position_coverage") or {}
    teams = []
    for i, (no, members) in enumerate(roster):
        ps = [players[pid] for pid, _ in members]
        hs = [h for h in (_height(p) for p in ps) if h]
        cov = coverage.get(str(no), {})
        teams.append({
            "team": al.squad(no, names[no]),
            "size": len(members),
            "avg_skill": avg[i] if i < len(avg) else None,
            "avg_height": round(mean(hs), 1) if hs else None,
            "guests": sum(1 for p in ps if p.kind == PlayerKind.GUEST),
            "unknown_skill": (m.get("unknown_skill_per_squad") or [0] * len(roster))[i],
            "has_handler": cov.get("handler"),
            "has_bigman": cov.get("bigman"),
            "players": [
                {"id": al.of(pid), "position": pos, "guest": players[pid].kind == PlayerKind.GUEST} for pid, pos in members
            ],
        })
    cs = constraints_of(cand.run)
    sizes = [len(ms) for _, ms in roster]
    squad_of = {pid: no for no, ms in roster for pid, _ in ms}
    mutual = sorted([al.of(a), al.of(b)] for a, b in _mutual_pairs(db, ids) if squad_of.get(a) == squad_of.get(b))
    payload = {
        "strategy": STRATEGY_LABEL[cand.strategy],
        "teams": teams,
        "balance": {"skill_spread": m.get("skill_spread")},
        "constraints_applied": {
            "same_team_groups": [[al.of(p) for p in g] for g in cs.lock_groups],
            "separate_groups": [[al.of(p) for p in g] for g in cs.separate_groups],
            "pinned": [{"player": al.of(p.player_id), "team": al.squad(p.squad_no, names.get(p.squad_no, ""))} for p in cs.pins],
            "team_sizes": sizes,
        },
        "mutual_pairs_same_team": mutual,
        "manually_edited": bool(m.get("manually_edited")),
    }
    fallback = {"summary": "", "reasons": [], "watch_point": "", "text": cand.explanation or ""}
    call = llm_guard.ChainCall(
        chain="A", schema=ExplainA,
        messages=[("system", SYSTEM_A), ("human", _json(payload))],
        payload=payload, aliases=al, fallback=fallback,
        key_parts={
            "v": PROMPT_VERSION, "candidate": cand.id, "strategy": cand.strategy, "roster": roster, "avg": avg,
            "spread": m.get("skill_spread"), "constraints": cs.model_dump(), "mutual": mutual,
        },
        usable=lambda o: bool(o.get("summary")) and any(r for r in o.get("reasons", [])),
        max_chars=80,
        post=lambda o: {**o, "reasons": [r for r in o["reasons"] if r][:3]},
    )
    out = llm_guard.run(db, call, user_id=user.id)
    o = out.output
    return AiExplanation(
        summary=o.get("summary", ""), reasons=o.get("reasons", []), watch_point=o.get("watch_point", ""),
        text=o.get("text") if out.fallback else None, fallback=out.fallback, cached=out.cached,
    )


# ---------------------------------------------------------------------------
# 체인 B — 팀원용 (팀마다 한 번)
# ---------------------------------------------------------------------------


def team_traits(ps: list[Player], positions: dict[int, str | None]) -> list[str]:
    """규칙으로 만든 팀 특징 태그. 실력 값은 넣지 않는다."""
    tall = sum(1 for p in ps if (_height(p) or 0) >= TALL_CM)
    pos = [positions.get(p.id) for p in ps]
    guards = sum(1 for x in pos if x in {g.value for g in GUARDS})
    bigs = sum(1 for x in pos if x in {b.value for b in BIGS})
    handlers = sum(1 for p in ps if any(pp.position == Position.PG and pp.can_play for pp in p.positions))
    guests = sum(1 for p in ps if p.kind == PlayerKind.GUEST)
    out = [f"모두 {len(ps)}명"]
    if tall:
        out.append(f"{TALL_CM}cm 이상 {tall}명")
    if guards:
        out.append(f"가드 {guards}명")
    if bigs:
        out.append(f"빅맨(4·5번) {bigs}명")
    if handlers:
        out.append(f"볼 운반 가능 {handlers}명")
    if guests:
        out.append(f"게스트 {guests}명")
    return out


def member_message(db: Session, event: Event, me: Player, user: User) -> AiMessage:
    cand = adopted_candidate(db, event)
    if cand is None:
        raise errors.NotAdoptedYet()
    roster = _roster(cand)
    mine = next(((no, ms) for no, ms in roster if any(pid == me.id for pid, _ in ms)), None)
    fallback_text = (cand.metrics or {}).get("player_explanation")
    if mine is None:  # 이 배정에 들지 않은 사람 (매니저가 안 뛰는 날 등)
        return AiMessage(message=None, fallback=True)
    no, members = mine
    ids = [pid for pid, _ in members]
    players = _players_of(db, ids)
    names = {sq.squad_no: sq.squad_name for sq in cand.squads}
    al = llm_guard.Aliases()
    team = al.squad(no, names[no])
    for pid in ids:
        al.player(pid, players[pid].display_name)
    positions = dict(members)
    pairs = _mutual_pairs(db, ids)
    picks = {pid: sorted(al.of(b if a == pid else a) for a, b in pairs if pid in (a, b)) for pid in ids}
    payload = {
        "team": team,
        "players": [{"id": al.of(pid), "position": pos} for pid, pos in members],
        "team_traits": team_traits([players[pid] for pid in ids], positions),
        "mutual_picks": [{"player": al.of(pid), "with": w} for pid, w in picks.items() if w],
    }

    def to_ids(o: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, str] = {}
        for item in o.get("messages", []):
            pid = al.player_id_of(item.get("player", ""))
            if pid is not None and item.get("message"):
                out[str(pid)] = item["message"]
        return {"by_player": out}

    call = llm_guard.ChainCall(
        chain="B", schema=TeamMessagesB,
        messages=[("system", SYSTEM_B), ("human", _json(payload))],
        payload=payload, aliases=al, fallback={"by_player": {}}, leak_check=True,
        key_parts={"v": PROMPT_VERSION, "candidate": cand.id, "squad": no, "roster": members, "picks": payload["mutual_picks"]},
        usable=lambda o: any(m.get("message") for m in o.get("messages", [])),
        max_chars=120, post=to_ids,
    )
    out = llm_guard.run(db, call, user_id=user.id)
    msg = out.output.get("by_player", {}).get(str(me.id))
    if not msg:
        return AiMessage(message=fallback_text, fallback=True)
    return AiMessage(message=msg, fallback=out.fallback)


def _json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
