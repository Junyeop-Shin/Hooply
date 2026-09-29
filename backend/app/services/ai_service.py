"""AI 배정 설명 (docs/07 F19, FR-51). 판단 재료는 ai_insight 가 규칙으로 만들고, 여기서 가명으로 바꿔 llm_guard 로 부른다.

  체인 A (매니저용)  후보안 하나 — 두 팀 색깔 요약 · 활약이 기대되는 선수 · 호흡이 좋을 조합 · 부족한 역할 · 주의할 점
  체인 B (팀원용)    확정 배정의 팀마다 **한 번** 불러 그 팀 선수 전원의 안내(포지션 이유 · 기대 역할 · 호흡 맞출 동료)를
                     한꺼번에 받는다 (T13: 16명이 열어도 2회)

B 입력에는 실력 값이 없다(NFR-04). 포지션 · 역할 · 본인 강점(설문에서 확인된 것만) · 동료와의 궁합만 보낸다.
실패하면 기존 규칙 설명 문장(A: candidate.explanation, B: metrics.player_explanation)을 대신 보여 준다.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core import errors
from app.llm import llm_guard
from app.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_A,
    SYSTEM_B,
    SYSTEM_C,
    ExplainA,
    TacticsC,
    TeamMessagesB,
)
from app.models import AssignmentCandidate, Event, Player, User
from app.models.enums import Position
from app.schemas.ai import AiExplanation, AiMessage, AiTacticItem, AiTactics
from app.services import tactic_service
from app.services.ai_insight import ROLE_KO, Insight, analyze
from app.services.assignment_service import (
    STRATEGY_LABEL,
    _players_of,
    adopted_candidate,
    constraints_of,
)


def _pos(value: Any) -> str | None:
    return value.value if isinstance(value, Position) else value


def _roster(cand: AssignmentCandidate) -> list[tuple[int, list[tuple[int, str | None]]]]:
    """[(squad_no, [(player_id, 배정 포지션)…])…] — 팀 번호 · player_id 순서로 고정 (가명 번호와 캐시 키가 매번 같게)."""
    return [
        (sq.squad_no, sorted((s.player_id, _pos(s.assigned_position)) for s in sq.slots))
        for sq in sorted(cand.squads, key=lambda s: s.squad_no)
    ]


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _player_view(ins: Insight, al: llm_guard.Aliases, pid: int) -> dict[str, Any]:
    p = ins.players[pid]
    return {
        "id": al.of(pid), "position": p.position, "position_why": p.position_why,
        "role": ROLE_KO[p.top_role], "strengths": p.strengths,
        "partners": [{"with": al.of(q), "why": why} for q, why in p.partners],
    }


# ---------------------------------------------------------------------------
# 체인 A — 매니저용
# ---------------------------------------------------------------------------


def explain_candidate(db: Session, cand: AssignmentCandidate, user: User) -> AiExplanation:
    roster = _roster(cand)
    ids = [pid for _, ms in roster for pid, _ in ms]
    players = _players_of(db, ids)
    event = db.get(Event, cand.run.event_id)
    ins = analyze(db, event, cand, players)
    names = {sq.squad_no: sq.squad_name for sq in cand.squads}
    al = llm_guard.Aliases()
    for no, members in roster:
        al.squad(no, names[no])
        for pid, _ in members:
            al.player(pid, players[pid].display_name)
    m = cand.metrics or {}
    teams = []
    for i, (no, members) in enumerate(roster):
        t = ins.teams[no]
        teams.append({
            "team": al.squad(no, names[no]),
            "size": len(members),
            "key_players": [
                {"player": al.of(pid), "role": ROLE_KO[ins.players[pid].top_role], "strengths": ins.players[pid].strengths}
                for pid in t.key_players
            ],
            "pairs": [{"players": [al.of(a), al.of(b)], "why": why} for a, b, why in t.pairs],
            "gaps": t.gaps,
            "players": [{"player": al.of(pid), "position": pos, "role": ROLE_KO[ins.players[pid].top_role]} for pid, pos in members],
            "guests_without_skill": (m.get("unknown_skill_per_squad") or [0] * len(roster))[i],
        })
    cs = constraints_of(cand.run)
    payload = {
        "strategy": STRATEGY_LABEL[cand.strategy],
        "balance": {"skill_spread": m.get("skill_spread")},
        "teams": teams,
        "constraints_applied": {
            "same_team_groups": [[al.of(p) for p in g] for g in cs.lock_groups],
            "separate_groups": [[al.of(p) for p in g] for g in cs.separate_groups],
            "pinned": [{"player": al.of(p.player_id), "team": al.squad(p.squad_no, names.get(p.squad_no, ""))} for p in cs.pins],
        },
    }
    fallback = {"summary": "", "key_players": [], "chemistry": [], "gaps": [], "watch_point": "", "text": cand.explanation or ""}
    call = llm_guard.ChainCall(
        chain="A", schema=ExplainA,
        messages=[("system", SYSTEM_A), ("human", _json(payload))],
        payload=payload, aliases=al, fallback=fallback,
        key_parts={"v": PROMPT_VERSION, "candidate": cand.id, "strategy": cand.strategy, "input": payload},
        usable=lambda o: bool(o.get("summary")) and bool(o.get("key_players") or o.get("chemistry")),
        max_chars=90,
        post=lambda o: {**o, "key_players": o["key_players"][:4], "chemistry": o["chemistry"][:3], "gaps": o["gaps"][:2]},
    )
    out = llm_guard.run(db, call, user_id=user.id)
    o = out.output
    return AiExplanation(
        summary=o.get("summary", ""), key_players=o.get("key_players", []), chemistry=o.get("chemistry", []),
        gaps=o.get("gaps", []), watch_point=o.get("watch_point", ""),
        text=o.get("text") if out.fallback else None, fallback=out.fallback, cached=out.cached,
    )


# ---------------------------------------------------------------------------
# 체인 B — 팀원용 (팀마다 한 번)
# ---------------------------------------------------------------------------


def member_message(db: Session, event: Event, me: Player, user: User) -> AiMessage:
    cand = adopted_candidate(db, event)
    if cand is None:
        raise errors.NotAdoptedYet()
    roster = _roster(cand)
    mine = next(((no, ms) for no, ms in roster if any(pid == me.id for pid, _ in ms)), None)
    fallback_text = (cand.metrics or {}).get("player_explanation")
    if mine is None:  # 이 배정에 들지 않은 사람 (매니저가 안 뛰는 날 등)
        return AiMessage(in_assignment=False, fallback=True)
    no, members = mine
    all_ids = [pid for _, ms in roster for pid, _ in ms]
    players = _players_of(db, all_ids)  # 역할 점수의 기준은 그날 참석자 전원
    ins = analyze(db, event, cand, players)
    names = {sq.squad_no: sq.squad_name for sq in cand.squads}
    al = llm_guard.Aliases()
    team = al.squad(no, names[no])
    ids = [pid for pid, _ in members]
    for pid in ids:
        al.player(pid, players[pid].display_name)
    payload = {"team": team, "players": [_player_view(ins, al, pid) for pid in ids]}

    def to_ids(o: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, dict[str, str]] = {}
        for item in o.get("messages", []):
            pid = al.player_id_of(item.get("player", ""))
            if pid is not None and item.get("role"):
                out[str(pid)] = {k: item.get(k, "") for k in ("why_position", "role", "partner")}
        return {"by_player": out}

    call = llm_guard.ChainCall(
        chain="B", schema=TeamMessagesB,
        messages=[("system", SYSTEM_B), ("human", _json(payload))],
        payload=payload, aliases=al, fallback={"by_player": {}}, leak_check=True,
        key_parts={"v": PROMPT_VERSION, "candidate": cand.id, "squad": no, "input": payload},
        usable=lambda o: any(m.get("role") for m in o.get("messages", [])),
        max_chars=90, post=to_ids,
    )
    out = llm_guard.run(db, call, user_id=user.id)
    mine_msg = out.output.get("by_player", {}).get(str(me.id))
    if not mine_msg:
        return AiMessage(fallback=True, text=fallback_text)
    return AiMessage(fallback=out.fallback, **mine_msg)


# ---------------------------------------------------------------------------
# 체인 C — 전술 추천 설명 (팀마다, 수비 보기마다 한 번)
# ---------------------------------------------------------------------------


def _rule_sentence(lu, names: dict[int, str]) -> str:
    """폴백: "적합도 81 · 허재 볼 핸들러(볼 운반·픽앤롤 핸들러) · …" — 강점이 있는 자리만."""
    parts = [f"적합도 {round(lu.fit)}"]
    for s in lu.slots:
        if s.matched_attrs:
            parts.append(f"{names[s.player_id]} {ROLE_KO[s.role]}({'·'.join(s.matched_attrs[:2])})")
    return " · ".join(parts)


def explain_tactics(db: Session, event: Event, me: Player, user: User, *, squad_no: int, zone: bool) -> AiTactics:
    ctx = tactic_service._context(db, event)
    tactic_service._require_attendee(db, event, me, ctx)
    if ctx is None:
        raise errors.NotAdoptedYet()
    if squad_no not in ctx.by_squad:
        raise errors.NotFound("그날 배정에 없는 팀이에요.")
    lineups = tactic_service.ranked_lineups(ctx, squad_no, zone=zone, manager=True)  # 강점은 모두에게 (점수는 넣지 않는다)
    if not lineups:
        return AiTactics(squad_no=squad_no, one_liner="", items=[], fallback=True)
    ids = ctx.by_squad[squad_no]
    names = {pid: ctx.players[pid].display_name for pid in ids}
    al = llm_guard.Aliases()
    team = al.squad(squad_no, ctx.names[squad_no])
    for pid in ids:
        al.player(pid, names[pid])
    height = {pid: (p.height_cm if p.user is None else p.user.height_cm) for pid, p in ctx.players.items()}
    position = {s.player_id: _pos(s.assigned_position) for sq in ctx.cand.squads for s in sq.slots}

    def notes(lu) -> list[str]:
        out = []
        for s in lu.slots:
            if any(m.startswith("설문 없음") for m in s.missing_attrs):
                out.append(f"{al.of(s.player_id)}는 설문 정보가 없어 역할을 추정했어요")
            elif s.score is not None and s.score < 50:
                out.append(f"{s.slot}번 자리({ROLE_KO[s.role]})는 딱 맞는 사람이 적어요")
        return out[:2]

    recs = [
        {
            "play_id": lu.play_key.removeprefix("preset:"), "name": lu.name, "summary": lu.summary, "fit": lu.fit,
            "slots": [
                {"slot": s.slot, "role": ROLE_KO[s.role], "player": al.of(s.player_id), "strengths": s.matched_attrs[:2],
                 "backups": [al.of(b.player_id) for b in s.backups]}
                for s in lu.slots
            ],
            "notes": notes(lu),
        }
        for lu in lineups
    ]
    payload = {
        "team": team, "zone": zone,
        "players": [{"id": al.of(pid), "position": position.get(pid), "height_cm": height.get(pid)} for pid in ids],
        "recommendations": recs,
    }
    play_ids = [r["play_id"] for r in recs]
    rule = {lu.play_key.removeprefix("preset:"): _rule_sentence(lu, names) for lu in lineups}
    fallback = {"one_liner": "", "items": [{"play_id": k, "reason": v, "key_roles": [], "caution": ""} for k, v in rule.items()]}

    def in_order(o: dict[str, Any]) -> dict[str, Any]:
        """추천 순서대로, 빠진 전술은 규칙 문장으로 채운다."""
        got = {it["play_id"]: it for it in o.get("items", [])}
        items = [got.get(k) or {"play_id": k, "reason": rule[k], "key_roles": [], "caution": ""} for k in play_ids]
        return {"one_liner": o.get("one_liner", ""), "items": [{**it, "key_roles": it["key_roles"][:3]} for it in items]}

    call = llm_guard.ChainCall(
        chain="C", schema=TacticsC,
        messages=[("system", SYSTEM_C), ("human", _json(payload))],
        payload=payload, aliases=al, fallback=fallback,
        key_parts={"v": PROMPT_VERSION, "presets": tactic_service.PRESETS_VERSION, "candidate": ctx.cand.id, "squad": squad_no, "input": payload},
        extra_check=lambda o: all(it.get("play_id") in play_ids for it in o.get("items", [])),
        usable=lambda o: any(it.get("reason") for it in o.get("items", [])),
        max_chars=90, post=in_order,
    )
    out = llm_guard.run(db, call, user_id=user.id)
    o = out.output
    return AiTactics(
        squad_no=squad_no, one_liner=o.get("one_liner", ""), fallback=out.fallback, cached=out.cached,
        items=[AiTacticItem(play_key=f"preset:{it['play_id']}", reason=it["reason"], key_roles=it["key_roles"], caution=it["caution"]) for it in o["items"]],
    )
