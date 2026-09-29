"""AI 배정 설명의 재료 — 규칙으로 판단한다 (docs/07 1.2 "판단은 규칙이, 문장은 LLM 이").

LLM 은 여기서 정한 사실만 문장으로 푼다. 그래서 "누가 활약할지 · 누구와 호흡이 좋을지 · 어떤 역할이 부족한지" 를
LLM 이 지어내지 않고, 설문 · 전술 역할 점수 · 선호 포지션 · 상호 지목에서 나온 근거가 늘 있다.

선수마다 (체인 B · A 공통)
  top_role        역할 점수(app/tactics/roles.py)가 가장 높은 역할 — "팀에서 기대하는 역할"
  strengths       그 역할에서 본인 설문으로 확인된 강점 (최대 2개, 게스트는 없음)
  position_why    배정 포지션의 이유 — 선호 순서, 팀 안 희소 자원(1번·빅맨)
  partners        호흡을 맞추면 좋을 동료 (최대 2명) — 서로 같이 뛰고 싶다고 고른 사이 먼저, 그다음 역할 궁합
팀마다 (체인 A)
  gaps            팀에서 가장 잘하는 사람도 점수가 낮은 역할 — "부족한 역할"
  key_players     실력 추정치 상위 2명과 그 역할 (매니저에게만)
  pairs           호흡이 좋을 조합 — 상호 지목 쌍, 역할 궁합 상위
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssignmentCandidate, ChemistryScore, Player
from app.models.enums import PlayerKind, Position
from app.services.tactic_service import role_scores_for
from app.tactics.play import ROLES, Role
from app.tactics.roles import PlayerRoles

ROLE_KO: dict[Role, str] = {
    "ball_handler": "볼 핸들러", "screener_roll": "스크린 후 골밑으로 들어가는 빅맨", "screener_pop": "스크린 후 외곽으로 빠지는 빅맨",
    "shooter": "슈터", "cutter": "공 없이 움직이는 커터", "post": "포스트업 빅맨", "spacer": "외곽에서 공간을 넓히는 역할",
}
# 팀에 꼭 있어야 하는 역할만 "부족한 역할" 로 본다 (스페이서·팝은 다른 역할이 겸한다)
CORE_ROLES: tuple[Role, ...] = ("ball_handler", "shooter", "post", "screener_roll", "cutter")
GAP_BELOW = 0.5  # 팀 최고 점수가 이 미만이면 부족
# 역할 궁합: (가, 나) → 이름. 순서 무관
PAIR_LABEL: dict[frozenset[str], str] = {
    frozenset({"ball_handler", "screener_roll"}): "픽앤롤",
    frozenset({"ball_handler", "screener_pop"}): "픽앤팝",
    frozenset({"ball_handler", "shooter"}): "돌파 후 킥아웃 3점",
    frozenset({"ball_handler", "cutter"}): "컷인 패스",
    frozenset({"ball_handler", "spacer"}): "돌파 후 킥아웃",
    frozenset({"post", "shooter"}): "인사이드-아웃",
    frozenset({"post", "cutter"}): "포스트에서 컷인 패스",
    frozenset({"post", "spacer"}): "인사이드-아웃",
    frozenset({"screener_roll", "shooter"}): "스크린으로 슈터 살리기",
}
GUARD_POS = {Position.PG}
BIG_POS = {Position.PF, Position.C}


@dataclass
class PlayerInsight:
    player_id: int
    squad_no: int
    position: str | None
    top_role: Role
    strengths: list[str]
    position_why: list[str]
    partners: list[tuple[int, str]] = field(default_factory=list)  # (동료 player_id, 이유)
    skill: float | None = None  # 매니저용 (A) 만 쓴다
    is_guest: bool = False


@dataclass
class TeamInsight:
    squad_no: int
    gaps: list[str]  # 부족한 역할 이름
    key_players: list[int]  # 활약이 기대되는 선수 (실력 추정 상위)
    pairs: list[tuple[int, int, str]]  # 호흡이 좋을 조합


@dataclass
class Insight:
    players: dict[int, PlayerInsight]
    teams: dict[int, TeamInsight]


def _top_role(pr: PlayerRoles) -> Role:
    return max(ROLES, key=lambda r: (pr.scores[r], -ROLES.index(r)))


def _skill(p: Player) -> float | None:
    prof = p.profile
    if prof is None or prof.skill_confidence == 0:
        return None
    v = prof.skill_overall if prof.skill_overall is not None else prof.prior_overall
    return float(v) if v is not None else None


def _position_why(p: Player, pos: str | None, team: list[Player]) -> list[str]:
    if pos is None:
        return []
    rows = {pp.position.value: pp for pp in p.positions}
    row = rows.get(pos)
    out = []
    if row is not None and row.preference_rank == 1:
        out.append("가장 선호하는 포지션")
    elif row is not None and row.preference_rank:
        out.append("두 번째 이후로 선호하는 포지션")
    elif row is not None and row.can_play:
        out.append("할 수 있다고 한 포지션")
    else:
        out.append("팀 구성상 맡은 포지션")

    def can(q: Player, group: set[Position]) -> bool:
        return any(pp.position in group and pp.can_play for pp in q.positions)

    if pos in {g.value for g in GUARD_POS}:
        n = sum(1 for q in team if can(q, GUARD_POS))
        if n <= 2:
            out.append(f"팀에서 1번(볼 운반)을 맡을 수 있는 사람이 {n}명뿐")
    if pos in {b.value for b in BIG_POS}:
        n = sum(1 for q in team if can(q, BIG_POS))
        if n <= 2:
            out.append(f"팀에서 골밑을 맡을 수 있는 사람이 {n}명뿐")
    return out


def mutual_pairs(db: Session, ids: list[int]) -> set[tuple[int, int]]:
    """서로 "또 같이 뛰고 싶다" 고 고른 쌍 (a < b)."""
    rows = db.execute(
        select(ChemistryScore.player_a_id, ChemistryScore.player_b_id).where(
            ChemistryScore.pref_mutual.is_(True), ChemistryScore.player_a_id.in_(ids), ChemistryScore.player_b_id.in_(ids),
        )
    ).all()
    return {(a, b) for a, b in rows}


def analyze(db: Session, event, cand: AssignmentCandidate, players: dict[int, Player]) -> Insight:
    """후보안(확정 전이든 후든) 하나의 선수·팀 판단. `players` 는 후보안에 든 사람 전원."""
    scores = role_scores_for(db, event, players)
    squads = {sq.squad_no: {s.player_id: s.assigned_position for s in sq.slots} for sq in cand.squads}
    mutual = mutual_pairs(db, list(players))
    out_p: dict[int, PlayerInsight] = {}
    for no, members in squads.items():
        team = [players[pid] for pid in members if pid in players]
        for pid, pos in members.items():
            if pid not in players:
                continue
            p, pr = players[pid], scores[pid]
            role = _top_role(pr)
            posv = pos.value if isinstance(pos, Position) else pos
            out_p[pid] = PlayerInsight(
                player_id=pid, squad_no=no, position=posv, top_role=role,
                strengths=pr.matched_attrs(role)[:2], position_why=_position_why(p, posv, team),
                skill=_skill(p), is_guest=p.kind == PlayerKind.GUEST,
            )

    # 호흡 맞출 동료: 상호 지목 먼저, 그다음 역할 궁합이 맞는 사람 중 두 사람 역할 점수 합이 큰 순
    for pid, me in out_p.items():
        mates = [q for q in out_p.values() if q.squad_no == me.squad_no and q.player_id != pid]
        chosen: list[tuple[int, str]] = []
        for q in mates:
            if tuple(sorted((pid, q.player_id))) in mutual:
                chosen.append((q.player_id, "서로 같이 뛰고 싶다고 고른 사이"))
        fits = sorted(
            (q for q in mates if frozenset({me.top_role, q.top_role}) in PAIR_LABEL and q.player_id not in dict(chosen)),
            key=lambda q: -(scores[pid].scores[me.top_role] + scores[q.player_id].scores[q.top_role]),
        )
        for q in fits:
            chosen.append((q.player_id, PAIR_LABEL[frozenset({me.top_role, q.top_role})]))
        me.partners = chosen[:2]

    out_t: dict[int, TeamInsight] = {}
    for no, members in squads.items():
        ids = [pid for pid in members if pid in out_p]
        gaps = [ROLE_KO[r] for r in CORE_ROLES if ids and max(scores[pid].scores[r] for pid in ids) < GAP_BELOW]
        known = sorted((pid for pid in ids if out_p[pid].skill is not None), key=lambda pid: -out_p[pid].skill)  # type: ignore[operator]
        pairs: list[tuple[int, int, str]] = [
            (a, b, "서로 같이 뛰고 싶다고 고른 사이") for a, b in sorted(mutual) if a in ids and b in ids
        ]
        seen = {frozenset(x[:2]) for x in pairs}
        combos = sorted(
            (
                (scores[a].scores[out_p[a].top_role] + scores[b].scores[out_p[b].top_role], a, b)
                for i, a in enumerate(ids) for b in ids[i + 1:]
                if frozenset({out_p[a].top_role, out_p[b].top_role}) in PAIR_LABEL and frozenset({a, b}) not in seen
            ),
            reverse=True,
        )
        for _, a, b in combos[: max(0, 2 - len(pairs)) or 1]:
            pairs.append((a, b, PAIR_LABEL[frozenset({out_p[a].top_role, out_p[b].top_role})]))
        out_t[no] = TeamInsight(squad_no=no, gaps=gaps, key_players=known[:2], pairs=pairs[:3])
    return Insight(players=out_p, teams=out_t)
