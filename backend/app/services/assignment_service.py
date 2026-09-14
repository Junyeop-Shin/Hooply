"""팀 배정 엔진 (설계서 9.5 ~ 9.7절 · F5 · F6 · F7 · F15 · F16).

흐름 (9.5절)
  1. 입력: 참석 확정자(회원+게스트), 팀 수 T, 회차별 제약(LOCK / SEPARATE / PIN)
  2. 실현가능성 사전 검사 → 실패면 422 + details (9.6절 표)
  3. PIN 은 그 팀에 고정, LOCK 은 Union-Find 로 **슈퍼노드** 로 축약 (제약 위반이 원천적으로 불가능)
  4. 2팀 · 12~14명 규모는 **완전 탐색** (조합 ≤ 수천 개, 9.7절) — 슈퍼노드 부분집합을 전부 평가
  5. 하드 제약: 각 팀에 1번(PG) 가능자 ≥ 1, 5번(PF/C) 가능자 ≥ 1. 만족하는 해가 없으면 경고 후 완화
  6. 목적함수 J 를 전략 3종 가중치로 각각 최소화 → 후보안 3개 (서로 다른 편성을 보장)
  7. 규칙 기반 설명 생성 (매니저용 수치 / 플레이어용 문장)

목적함수 (9.5절 7단계)
  J = w_skill·(팀 평균 실력 차)  + w_position·(포지션 커버리지 결손)
    + w_pref·(−팀 내 선호 조합)   + w_role·(선호 포지션 미충족)
    + w_fair·(최근 회차 같은 팀 반복) + w_guest·(게스트 편중)

지금은 2팀만 지원한다 (13.1절 Q4 — 현재 운영이 2팀 고정). 3팀 이상은 422 로 안내한다.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import errors
from app.core.errors import ErrorDetail
from app.models import (
    AssignmentCandidate,
    AssignmentConstraint,
    AssignmentRun,
    AssignmentSlot,
    AssignmentSquad,
    ChemistryScore,
    Event,
    EventAttendance,
    Player,
    User,
)
from app.models.enums import (
    AttendanceStatus,
    ConstraintType,
    EventStatus,
    PlayerKind,
    Position,
    Strategy,
    TeamRole,
)
from app.schemas.assignment import (
    AdoptedAssignment,
    AssignmentRunRequest,
    AssignmentRunView,
    CandidateView,
    ConstraintSet,
    ConstraintViolation,
    Exchange,
    MovePlayer,
    PinConstraint,
    SwapPair,
    ValidateResult,
)
from app.schemas.common import SquadView
from app.services.player_service import to_card

SQUAD_NAMES = ["블랙", "화이트", "레드", "블루"]  # 13.1절 Q6 기본값
MAX_SUPERNODES = 18  # 완전 탐색 상한 (2^18 ≈ 26만, 약 0.6초). 초과 시 안내 — 실측 22개는 10초라 내렸다
HARD_PENALTY = 10.0
MIN_SQUAD_SIZE = 5  # 수동 수정 후에도 출전 5명은 남아야 한다

# 9.5절 전략별 가중치 표 + 공통 w_fair / w_guest
STRATEGY_WEIGHTS: dict[Strategy, dict[str, float]] = {
    Strategy.SKILL: {"skill": 0.70, "position": 0.15, "pref": 0.05, "role": 0.10},
    Strategy.CHEMISTRY: {"skill": 0.30, "position": 0.15, "pref": 0.40, "role": 0.15},
    Strategy.BALANCED: {"skill": 0.45, "position": 0.25, "pref": 0.15, "role": 0.15},
}
W_FAIR = 0.05
W_GUEST = 0.05
STRATEGY_LABEL = {Strategy.SKILL: "실력 우선", Strategy.CHEMISTRY: "친화도 우선", Strategy.BALANCED: "종합"}


# ---------------------------------------------------------------------------
# 입력 준비
# ---------------------------------------------------------------------------


@dataclass
class RosterPlayer:
    player: Player
    skill: float  # skill_overall 또는 prior_overall, 없으면 팀 평균
    known: bool  # 실력 정보가 있는지 (게스트 미지정 → False)
    playable: set[Position]
    primary: Position | None
    pref_rank: dict[Position, int]

    @property
    def id(self) -> int:
        return self.player.id

    @property
    def is_guest(self) -> bool:
        return self.player.kind == PlayerKind.GUEST

    @property
    def can_handle(self) -> bool:
        return Position.PG in self.playable

    @property
    def can_big(self) -> bool:
        return bool(self.playable & {Position.PF, Position.C})


def build_roster(db: Session, event: Event) -> list[RosterPlayer]:
    """이 회차 ATTEND 참가자를 배정 입력으로 변환한다."""
    rows = db.execute(
        select(Player)
        .join(EventAttendance, EventAttendance.player_id == Player.id)
        .where(EventAttendance.event_id == event.id, EventAttendance.status == AttendanceStatus.ATTEND)
        .options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))
        .order_by(Player.display_name)
    ).scalars().all()
    known = []
    for p in rows:
        prof = p.profile
        v = prof.skill_overall if prof and prof.skill_overall is not None else (prof.prior_overall if prof else None)
        if v is not None and not (prof and prof.skill_confidence == 0):
            known.append(float(v))
    default = mean(known) if known else 0.0
    roster = []
    for p in rows:
        prof = p.profile
        v = prof.skill_overall if prof and prof.skill_overall is not None else (prof.prior_overall if prof else None)
        is_known = v is not None and not (prof and prof.skill_confidence == 0)
        playable = {pp.position for pp in p.positions if pp.can_play}
        ranked = sorted((pp for pp in p.positions if pp.can_play and pp.preference_rank), key=lambda x: x.preference_rank)
        roster.append(
            RosterPlayer(
                player=p, skill=float(v) if is_known else default, known=is_known, playable=playable,
                primary=ranked[0].position if ranked else None, pref_rank={pp.position: pp.preference_rank for pp in ranked},
            )
        )
    return roster


def _squad_sizes(n: int, t: int) -> list[int]:
    """N명을 T팀으로 최대한 고르게. 13명 2팀 → [7, 6]."""
    base, extra = divmod(n, t)
    return [base + (1 if i < extra else 0) for i in range(t)]


# ---------------------------------------------------------------------------
# 제약 → 슈퍼노드 (9.6절)
# ---------------------------------------------------------------------------


@dataclass
class Prepared:
    roster: dict[int, RosterPlayer]
    team_count: int
    sizes: list[int]
    supernodes: list[list[int]]  # 각 슈퍼노드의 player_id 목록
    node_of: dict[int, int]  # player_id → 슈퍼노드 index
    pins: dict[int, int]  # 슈퍼노드 index → squad index (0-based)
    separate_pairs: set[tuple[int, int]]  # 슈퍼노드 index 쌍
    lock_groups: list[list[int]]
    separate_groups: list[list[int]]
    pin_list: list[PinConstraint]
    violations: list[ConstraintViolation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def prepare(roster: list[RosterPlayer], body: AssignmentRunRequest) -> Prepared:
    """제약을 검증하고 슈퍼노드로 축약한다. 위반은 violations 에 모아 돌려준다 (예외를 던지지 않는다)."""
    rmap = {r.id: r for r in roster}
    t = body.team_count
    n = len(roster)
    v: list[ConstraintViolation] = []
    warnings: list[str] = []
    c = body.constraints

    if t != 2:
        v.append(ConstraintViolation(code="VALIDATION_ERROR", message="현재는 2팀 배정만 지원해요."))
    if n < t * 5:
        v.append(ConstraintViolation(code="NOT_ENOUGH_PLAYERS", message=f"{t}팀을 만들려면 최소 {t * 5}명이 필요해요 (현재 {n}명)"))

    # 알 수 없는 참가자
    referenced = {pid for g in c.lock_groups + c.separate_groups for pid in g} | {p.player_id for p in c.pins}
    unknown = sorted(pid for pid in referenced if pid not in rmap)
    if unknown:
        v.append(ConstraintViolation(code="PLAYER_NOT_IN_TEAM", message="참석 확정자가 아닌 인원이 제약에 들어 있어요.", player_ids=unknown))

    sizes = _squad_sizes(n, t) if t > 0 else []
    capacity = max(sizes) if sizes else 0

    # Union-Find 로 LOCK 병합
    parent = {pid: pid for pid in rmap}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for gi, g in enumerate(c.lock_groups):
        ids = [pid for pid in g if pid in rmap]
        for a, b in itertools.pairwise(ids):
            parent[find(a)] = find(b)
    groups: dict[int, list[int]] = defaultdict(list)
    for pid in rmap:
        groups[find(pid)].append(pid)
    supernodes = sorted(groups.values(), key=lambda ids: (-len(ids), ids[0]))
    node_of = {pid: i for i, ids in enumerate(supernodes) for pid in ids}

    for i, ids in enumerate(supernodes):
        if len(ids) > capacity > 0:
            v.append(ConstraintViolation(code="LOCK_GROUP_TOO_LARGE", message=f"묶음 그룹 인원({len(ids)}명)이 팀 정원({capacity}명)을 넘어요.", player_ids=ids, group_no=i))

    # SEPARATE: 슈퍼노드 쌍으로 변환. 같은 슈퍼노드 안에 있으면 충돌
    sep_pairs: set[tuple[int, int]] = set()
    for gi, g in enumerate(c.separate_groups):
        ids = [pid for pid in g if pid in rmap]
        for a, b in itertools.combinations(ids, 2):
            na, nb = node_of[a], node_of[b]
            if na == nb:
                v.append(ConstraintViolation(code="CONSTRAINT_CONFLICT", message="같은 팀으로 묶은 사람을 갈라놓을 수는 없어요.", player_ids=[a, b], group_no=gi))
            else:
                sep_pairs.add((min(na, nb), max(na, nb)))

    # PIN: 슈퍼노드 단위. 같은 묶음이 서로 다른 팀에 고정되면 충돌, 팀 정원 초과면 SQUAD_OVERFLOW
    pins: dict[int, int] = {}
    for p in c.pins:
        if p.player_id not in rmap:
            continue
        if not (1 <= p.squad_no <= t):
            v.append(ConstraintViolation(code="VALIDATION_ERROR", message=f"팀 번호는 1~{t} 사이여야 해요.", player_ids=[p.player_id]))
            continue
        node = node_of[p.player_id]
        sq = p.squad_no - 1
        if node in pins and pins[node] != sq:
            v.append(ConstraintViolation(code="CONSTRAINT_CONFLICT", message="같은 묶음의 사람이 서로 다른 팀에 배치됐어요.", player_ids=supernodes[node]))
        pins[node] = sq
    pinned_count = [0] * t
    for node, sq in pins.items():
        pinned_count[sq] += len(supernodes[node])
    for sq, cnt in enumerate(pinned_count):
        if sizes and cnt > sizes[sq]:
            v.append(ConstraintViolation(code="SQUAD_OVERFLOW", message=f"{SQUAD_NAMES[sq]} 팀에 정원({sizes[sq]}명)보다 많은 {cnt}명이 배치됐어요."))
    # SEPARATE 인데 같은 팀에 PIN
    for a, b in sep_pairs:
        if a in pins and b in pins and pins[a] == pins[b]:
            v.append(ConstraintViolation(code="SEPARATE_INFEASIBLE", message="갈라놓기로 지정한 두 사람이 같은 팀에 배치됐어요.", player_ids=supernodes[a] + supernodes[b]))

    if len(supernodes) > MAX_SUPERNODES:
        v.append(ConstraintViolation(code="VALIDATION_ERROR", message=f"참석 인원이 너무 많아요 (묶음 후 {len(supernodes)}개). 18개 이하로 줄여 주세요."))

    # 경고 (차단 아님)
    handlers = sum(1 for r in roster if r.can_handle)
    bigs = sum(1 for r in roster if r.can_big)
    if roster and handlers < t:
        warnings.append(f"1번(핸들러) 가능 인원이 {handlers}명이라 팀당 1명을 채우기 어려워요")
    if roster and bigs < t:
        warnings.append(f"빅맨(4·5번) 가능 인원이 {bigs}명이라 팀당 1명을 채우기 어려워요")
    unknown_guests = [r for r in roster if r.is_guest and not r.known]
    if unknown_guests:
        warnings.append(f"게스트 {len(unknown_guests)}명은 실력 정보가 없어 클럽 평균으로 가정해요")

    return Prepared(
        roster=rmap, team_count=t, sizes=sizes, supernodes=supernodes, node_of=node_of, pins=pins,
        separate_pairs=sep_pairs, lock_groups=[ids for ids in supernodes if len(ids) > 1],
        separate_groups=[[pid for pid in g if pid in rmap] for g in c.separate_groups], pin_list=[p for p in c.pins if p.player_id in rmap],
        violations=v, warnings=warnings,
    )


# ---------------------------------------------------------------------------
# 완전 탐색 (2팀)
# ---------------------------------------------------------------------------


def enumerate_partitions(prep: Prepared):
    """슈퍼노드를 두 팀으로 나누는 모든 방법을 (squad index per node) 튜플로 낸다. PIN·SEPARATE·정원을 지킨다."""
    nodes = list(range(len(prep.supernodes)))
    free = [i for i in nodes if i not in prep.pins]
    size = [len(prep.supernodes[i]) for i in nodes]
    need0 = prep.sizes[0] - sum(size[i] for i, sq in prep.pins.items() if sq == 0)
    if need0 < 0:
        return
    # 대칭 제거: PIN 이 없으면 첫 자유 노드는 항상 팀 0 (블랙/화이트 이름만 바뀌는 중복 해 제거)
    anchor = free[0] if free and not prep.pins else None
    sizes_free = sorted(size[i] for i in free)
    for k in range(len(free) + 1):
        # 가지치기: k개 노드로는 need0 를 못 채우는 k 는 조합을 아예 만들지 않는다
        if sum(sizes_free[:k]) > need0 or sum(sizes_free[len(free) - k:]) < need0:
            continue
        for subset in itertools.combinations(free, k):
            if anchor is not None and anchor not in subset:
                continue
            if sum(size[i] for i in subset) != need0:
                continue
            assign = dict(prep.pins)
            for i in free:
                assign[i] = 0 if i in subset else 1
            if any(assign[a] == assign[b] for a, b in prep.separate_pairs):
                continue
            yield tuple(assign[i] for i in nodes)


# ---------------------------------------------------------------------------
# 목적함수
# ---------------------------------------------------------------------------


@dataclass
class Scored:
    partition: tuple[int, ...]
    squads: list[list[RosterPlayer]]
    terms: dict[str, float]
    hard_ok: bool

    def total(self, w: dict[str, float]) -> float:
        j = (
            w["skill"] * self.terms["skill"] + w["position"] * self.terms["position"]
            + w["pref"] * self.terms["pref"] + w["role"] * self.terms["role"]
            + W_FAIR * self.terms["fair"] + W_GUEST * self.terms["guest"]
        )
        return j + (0.0 if self.hard_ok else HARD_PENALTY)


def _load_pref_pairs(db: Session, player_ids: list[int]) -> dict[tuple[int, int], float]:
    """선호 조합 (9.4절 1차 층): chemistry_scores.pref_score, 상호 지목이면 가중."""
    rows = db.scalars(
        select(ChemistryScore).where(ChemistryScore.player_a_id.in_(player_ids), ChemistryScore.player_b_id.in_(player_ids))
    ).all()
    out = {}
    for r in rows:
        if r.pref_score is None:
            continue
        out[(r.player_a_id, r.player_b_id)] = float(r.pref_score) * (1.5 if r.pref_mutual else 1.0)
    return out


def _load_recent_pairs(db: Session, event: Event, limit_events: int = 3) -> set[tuple[int, int]]:
    """최근 회차에서 같은 팀이었던 쌍 (w_fair)."""
    prev = db.scalars(
        select(Event).where(Event.team_id == event.team_id, Event.id != event.id, Event.event_date <= event.event_date)
        .order_by(Event.event_date.desc(), Event.id.desc()).limit(limit_events)
    ).all()
    pairs: set[tuple[int, int]] = set()
    for e in prev:
        cand = db.scalar(
            select(AssignmentCandidate).join(AssignmentRun).where(AssignmentRun.event_id == e.id, AssignmentCandidate.is_adopted.is_(True))
            .options(selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots))
        )
        if cand is None:
            continue
        for sq in cand.squads:
            ids = sorted(s.player_id for s in sq.slots)
            pairs.update(itertools.combinations(ids, 2))
    return pairs


def score_partition(prep: Prepared, partition: tuple[int, ...], pref_pairs: dict, recent_pairs: set) -> Scored:
    squads: list[list[RosterPlayer]] = [[] for _ in range(prep.team_count)]
    for node, sq in enumerate(partition):
        for pid in prep.supernodes[node]:
            squads[sq].append(prep.roster[pid])
    all_skills = [r.skill for r in prep.roster.values()]
    sd = pstdev(all_skills) if len(all_skills) > 1 else 0.0
    means = [mean(r.skill for r in s) if s else 0.0 for s in squads]
    # skill: 팀 평균 차이를 실력 표준편차로 정규화 (0 = 완전 균형)
    skill = (max(means) - min(means)) / max(sd, 0.5)

    # position: 하드 제약 결손 + 포지션 분포 불균형
    hard_ok = True
    missing = 0
    for s in squads:
        if not any(r.can_handle for r in s):
            missing += 1
            hard_ok = False
        if not any(r.can_big for r in s):
            missing += 1
            hard_ok = False
    counts = []
    for s in squads:
        c = {pos: 0 for pos in Position}
        for r in s:
            if r.primary:
                c[r.primary] += 1
        counts.append(c)
    imbalance = sum(abs(counts[0][pos] - counts[1][pos]) for pos in Position) / max(1, len(prep.roster)) if prep.team_count == 2 else 0.0
    position = missing + imbalance

    # role: 같은 팀에서 같은 주 포지션이 과다 (정원 5 기준 포지션당 1자리, 팀 인원이 많으면 2자리)
    role = 0.0
    for s, c in zip(squads, counts, strict=True):
        slots = 1 if len(s) <= 5 else 2
        role += sum(max(0, cnt - slots) for cnt in c.values())
    role /= max(1, len(prep.roster))

    # pref: 팀 내 선호 조합 합 (클수록 좋음 → 음수로)
    pref = 0.0
    for s in squads:
        ids = sorted(r.id for r in s)
        for a, b in itertools.combinations(ids, 2):
            pref += pref_pairs.get((a, b), 0.0)
    pref = -pref / max(1, len(prep.roster) / 2)

    # fair: 최근 회차 같은 팀 반복 쌍 비율
    repeats = 0
    for s in squads:
        ids = sorted(r.id for r in s)
        repeats += sum(1 for pair in itertools.combinations(ids, 2) if pair in recent_pairs)
    fair = repeats / max(1, len(recent_pairs)) if recent_pairs else 0.0

    # guest: 게스트(특히 데이터 없는) 편중
    gcounts = [sum(1 for r in s if r.is_guest) for s in squads]
    guest = (max(gcounts) - min(gcounts)) / max(1, sum(gcounts)) if sum(gcounts) else 0.0

    return Scored(partition=partition, squads=squads, terms={"skill": skill, "position": position, "pref": pref, "role": role, "fair": fair, "guest": guest, "means": means}, hard_ok=hard_ok)


# ---------------------------------------------------------------------------
# 포지션 배정 · 지표 · 설명
# ---------------------------------------------------------------------------


def assign_positions(squad: list[RosterPlayer]) -> dict[int, Position | None]:
    """팀 안에서 슬롯(PG, C, SG, SF, PF)을 선호 순위가 좋은 사람부터 채운다. 남는 사람은 주 포지션."""
    out: dict[int, Position | None] = {}
    remaining = list(squad)
    for pos in (Position.PG, Position.C, Position.SG, Position.SF, Position.PF):
        cands = [r for r in remaining if pos in r.playable]
        if not cands:
            continue
        best = min(cands, key=lambda r: r.pref_rank.get(pos, 9))
        out[best.id] = pos
        remaining.remove(best)
    for r in remaining:
        out[r.id] = r.primary
    return out


def metrics_of(sc: Scored) -> dict:
    means = sc.terms["means"]
    return {
        "squad_avg_skill": [round(m, 2) for m in means],
        "skill_spread": round(max(means) - min(means), 2),
        "position_coverage": {
            str(i + 1): {
                "handler": any(r.can_handle for r in s), "bigman": any(r.can_big for r in s),
                "primary_counts": {pos.value: sum(1 for r in s if r.primary == pos) for pos in Position},
            }
            for i, s in enumerate(sc.squads)
        },
        "guest_count_per_squad": [sum(1 for r in s if r.is_guest) for s in sc.squads],
        "unknown_skill_per_squad": [sum(1 for r in s if not r.known) for s in sc.squads],
        "terms": {k: round(v, 3) for k, v in sc.terms.items() if k != "means"},
        "hard_constraints_met": sc.hard_ok,
    }


def explain_manager(sc: Scored, strategy: Strategy, prep: Prepared) -> str:
    means = sc.terms["means"]
    names = SQUAD_NAMES
    gap = max(means) - min(means)
    lines = [
        f"[{STRATEGY_LABEL[strategy]}] " + " · ".join(f"{names[i]} {len(sc.squads[i])}명" for i in range(len(means)))
        + f" — 두 팀이 붙으면 한 쿼터에 약 {gap:.1f}점 차가 날 것으로 예상돼요 (0에 가까울수록 균형)."
    ]
    if sc.hard_ok:
        lines.append("양 팀 모두 1번(볼 운반)·5번(골밑) 가능 인원을 확보했어요.")
    else:
        lines.append("⚠ 오늘 인원으로는 한쪽 팀에 볼 운반이나 골밑을 맡을 사람이 없어요.")
    if prep.pin_list:
        lines.append(f"사전 배치 {len(prep.pin_list)}명은 지정한 팀에 고정했어요.")
    unknown = [r for s in sc.squads for r in s if r.is_guest and not r.known]
    if unknown:
        lines.append(f"게스트 {len(unknown)}명({', '.join(r.player.display_name for r in unknown)})은 실력 정보가 없어 클럽 평균으로 계산했어요.")
    graded = [r for s in sc.squads for r in s if r.is_guest and r.known]
    if graded:
        lines.append(f"게스트 {len(graded)}명은 등록자가 지정한 등급으로 계산했어요.")
    if sc.terms["fair"] > 0:
        lines.append("최근 회차와 같은 팀이 반복되는 조합이 일부 있어요.")
    return "\n".join(lines)


def explain_player(sc: Scored, positions: dict[int, Position | None]) -> str:
    lines = ["실력이 비슷하도록 두 팀을 나눴어요."]
    if sc.hard_ok:
        lines.append("각 팀에 볼 운반과 골밑을 맡을 수 있는 사람이 있어요.")
    got = sum(1 for s in sc.squads for r in s if r.primary and positions.get(r.id) == r.primary)
    total = sum(1 for s in sc.squads for r in s if r.primary)
    if total:
        lines.append(f"{total}명 중 {got}명이 가장 선호하는 포지션을 받았어요.")
    return " ".join(lines)


# ---------------------------------------------------------------------------
# 실행 · 저장
# ---------------------------------------------------------------------------


def validate(db: Session, event: Event, body: AssignmentRunRequest) -> ValidateResult:
    roster = build_roster(db, event)
    prep = prepare(roster, body)
    if prep.violations:
        return ValidateResult(feasible=False, violations=prep.violations, warnings=prep.warnings)
    # 분할 가능성: 해가 하나라도 있는지
    if next(enumerate_partitions(prep), None) is None:
        code = "SEPARATE_INFEASIBLE" if prep.separate_pairs else "LOCK_PARTITION_INFEASIBLE"
        msg = "갈라놓기 제약을 모두 만족하는 팀 구성이 없어요." if prep.separate_pairs else _partition_msg(prep)
        return ValidateResult(feasible=False, violations=[ConstraintViolation(code=code, message=msg)], warnings=prep.warnings)
    return ValidateResult(feasible=True, warnings=prep.warnings)


def _partition_msg(prep: Prepared) -> str:
    sizes = sorted((len(ids) for ids in prep.supernodes if len(ids) > 1), reverse=True)
    return f"{'명 그룹과 '.join(str(x) for x in sizes)}명 그룹으로는 {' · '.join(str(s) for s in prep.sizes)}명씩 두 팀을 만들 수 없어요."


def _raise_violations(vr: ValidateResult) -> None:
    first = vr.violations[0]
    cls = {
        "NOT_ENOUGH_PLAYERS": errors.NotEnoughPlayers, "LOCK_GROUP_TOO_LARGE": errors.LockGroupTooLarge,
        "CONSTRAINT_CONFLICT": errors.ConstraintConflict, "SEPARATE_INFEASIBLE": errors.SeparateInfeasible,
        "LOCK_PARTITION_INFEASIBLE": errors.LockPartitionInfeasible, "SQUAD_OVERFLOW": errors.SquadOverflow,
        "PLAYER_NOT_IN_TEAM": errors.PlayerNotInTeam,
    }.get(first.code, errors.ValidationError)
    raise cls(first.message, details=[ErrorDetail(field=str(v.player_ids) if v.player_ids else None, reason=v.message) for v in vr.violations])


def run(db: Session, event: Event, by: User, body: AssignmentRunRequest) -> AssignmentRun:
    """배정 실행: 검증 → 완전 탐색 → 전략별 후보안 저장.

    실행 기록을 쌓아 두지 않는다. 확정하지 않고 흘려보낸 지난 실행은 여기서 지우고, 확정한 편성만
    `adopt()` 때까지 남긴다 — 그래야 새 안을 짜 보는 동안에도 플레이어에게 직전 배정이 계속 보인다.
    """
    if event.status == EventStatus.CANCELED:
        raise errors.ValidationError("취소된 일정은 배정할 수 없어요.")
    vr = validate(db, event, body)
    if not vr.feasible:
        _raise_violations(vr)
    roster = build_roster(db, event)
    prep = prepare(roster, body)
    ids = [r.id for r in roster]
    pref_pairs = _load_pref_pairs(db, ids)
    recent = _load_recent_pairs(db, event)
    scored = [score_partition(prep, part, pref_pairs, recent) for part in enumerate_partitions(prep)]
    if any(s.hard_ok for s in scored):
        pool = [s for s in scored if s.hard_ok]
    else:
        pool = scored
        prep.warnings.append("양 팀에 볼 운반·골밑 자원을 다 넣을 수 없어 이 조건은 접었어요")

    _drop_unadopted_runs(db, event)  # 검증을 통과한 뒤에 정리한다 — 실패한 실행 때문에 지난 안을 잃지 않도록
    run_row = AssignmentRun(
        event_id=event.id, executed_by=by.id, team_count=body.team_count,
        params={"strategies": [s.value for s in body.strategies], "weights": {k.value: v for k, v in STRATEGY_WEIGHTS.items()}, "w_fair": W_FAIR, "w_guest": W_GUEST, "search": "exhaustive", "partitions_evaluated": len(scored)},
        roster_snapshot=[
            {"player_id": r.id, "name": r.player.display_name, "kind": r.player.kind, "skill": round(r.skill, 2), "known": r.known,
             "playable": sorted(p.value for p in r.playable), "primary": r.primary.value if r.primary else None}
            for r in roster
        ],
    )
    db.add(run_row)
    db.flush()
    for gi, g in enumerate(prep.lock_groups):
        for pid in g:
            db.add(AssignmentConstraint(run_id=run_row.id, type=ConstraintType.LOCK, group_no=gi + 1, player_id=pid))
    for gi, g in enumerate(prep.separate_groups):
        for pid in g:
            db.add(AssignmentConstraint(run_id=run_row.id, type=ConstraintType.SEPARATE, group_no=gi + 1, player_id=pid))
    for p in prep.pin_list:
        db.add(AssignmentConstraint(run_id=run_row.id, type=ConstraintType.PIN, player_id=p.player_id, squad_no=p.squad_no))

    used: set[tuple[int, ...]] = set()
    for strategy in body.strategies:
        w = STRATEGY_WEIGHTS[strategy]
        ordered = sorted(pool, key=lambda s: s.total(w))
        pick = next((s for s in ordered if s.partition not in used), ordered[0])  # 후보안끼리 편성이 달라야 고를 이유가 생긴다
        used.add(pick.partition)
        _persist_candidate(db, run_row, strategy, pick, prep)
    db.commit()
    db.refresh(run_row)
    return run_row


def _drop_unadopted_runs(db: Session, event: Event) -> None:
    """확정되지 않은 지난 실행을 지운다. 확정된 편성은 새 안을 확정할 때까지 남겨 둔다."""
    for old_run in db.scalars(
        select(AssignmentRun).where(AssignmentRun.event_id == event.id)
        .options(selectinload(AssignmentRun.candidates))
    ).all():
        if not any(c.is_adopted for c in old_run.candidates):
            db.delete(old_run)
    db.flush()


def _persist_candidate(db: Session, run_row: AssignmentRun, strategy: Strategy, sc: Scored, prep: Prepared) -> AssignmentCandidate:
    positions: dict[int, Position | None] = {}
    cand = AssignmentCandidate(
        run_id=run_row.id, strategy=strategy, total_score=Decimal(str(round(sc.total(STRATEGY_WEIGHTS[strategy]), 3))),
        metrics=metrics_of(sc), explanation=explain_manager(sc, strategy, prep),
    )
    db.add(cand)
    db.flush()
    for i, s in enumerate(sc.squads):
        pos = assign_positions(s)
        positions.update(pos)
        squad = AssignmentSquad(candidate_id=cand.id, squad_no=i + 1, squad_name=SQUAD_NAMES[i], avg_skill=Decimal(str(round(sc.terms["means"][i], 1))))
        db.add(squad)
        db.flush()
        for r in s:
            db.add(AssignmentSlot(squad_id=squad.id, player_id=r.id, assigned_position=pos.get(r.id)))
    cand.metrics = {
        **cand.metrics, "player_explanation": explain_player(sc, positions),
        # 수동 수정 초기화용 원본 편성 (squad_no → player_ids)
        "original_squads": {str(i + 1): [r.id for r in s] for i, s in enumerate(sc.squads)},
    }
    db.flush()
    return cand


# ---------------------------------------------------------------------------
# 조회 · 수정 · 확정
# ---------------------------------------------------------------------------


def _load_run(db: Session, run_id: int) -> AssignmentRun:
    r = db.get(
        AssignmentRun, run_id,
        options=[selectinload(AssignmentRun.constraints), selectinload(AssignmentRun.candidates).selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots)],
    )
    if r is None:
        raise errors.NotFound("팀 배정 기록을 찾을 수 없어요.")
    return r


def _players_of(db: Session, ids: list[int]) -> dict[int, Player]:
    return {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(ids)).options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user), selectinload(Player.user))).all()}


def _avg_height(players: list[Player]) -> float | None:
    hs = [h for h in ((p.height_cm if p.user is None else p.user.height_cm) for p in players) if h]  # 게스트 키(players.height_cm) 포함
    return round(mean(hs), 1) if hs else None


def squad_views(db: Session, cand: AssignmentCandidate, *, mask: bool) -> list[SquadView]:
    ids = [s.player_id for sq in cand.squads for s in sq.slots]
    players = _players_of(db, ids)
    out = []
    for sq in sorted(cand.squads, key=lambda x: x.squad_no):
        rows = [players[s.player_id] for s in sq.slots if s.player_id in players]
        members = [to_card(p, include_grade=not mask) for p in rows]
        members.sort(key=lambda c: (c.kind == "GUEST", c.display_name))
        out.append(
            SquadView(
                squad_no=sq.squad_no, squad_name=sq.squad_name, avg_skill=None if mask else sq.avg_skill, members=members,
                assigned_positions={s.player_id: s.assigned_position for s in sq.slots},
                manual_override_ids=[s.player_id for s in sq.slots if s.is_manual_override],
                avg_height_cm=_avg_height(rows),
            )
        )
    return out


def constraints_of(run_row: AssignmentRun) -> ConstraintSet:
    locks: dict[int, list[int]] = defaultdict(list)
    seps: dict[int, list[int]] = defaultdict(list)
    pins = []
    for c in run_row.constraints:
        if c.type == ConstraintType.LOCK:
            locks[c.group_no].append(c.player_id)
        elif c.type == ConstraintType.SEPARATE:
            seps[c.group_no].append(c.player_id)
        else:
            pins.append(PinConstraint(player_id=c.player_id, squad_no=c.squad_no))
    return ConstraintSet(lock_groups=list(locks.values()), separate_groups=list(seps.values()), pins=pins)


def candidate_view(db: Session, cand: AssignmentCandidate, *, mask: bool = False) -> CandidateView:
    return CandidateView(
        id=cand.id, strategy=cand.strategy, total_score=cand.total_score, metrics=cand.metrics,
        explanation=cand.metrics.get("player_explanation") if mask else cand.explanation,
        is_adopted=cand.is_adopted, squads=squad_views(db, cand, mask=mask),
    )


def run_view(db: Session, run_row: AssignmentRun, warnings: list[str] | None = None) -> AssignmentRunView:
    return AssignmentRunView(
        id=run_row.id, event_id=run_row.event_id, team_count=run_row.team_count, created_at=run_row.created_at,
        constraints=constraints_of(run_row), candidates=[candidate_view(db, c) for c in run_row.candidates],
        warnings=warnings or [],
    )


def list_runs(db: Session, event: Event) -> list[AssignmentRunView]:
    rows = db.scalars(
        select(AssignmentRun).where(AssignmentRun.event_id == event.id)
        .options(selectinload(AssignmentRun.constraints), selectinload(AssignmentRun.candidates).selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots))
        .order_by(AssignmentRun.created_at.desc())
    ).all()
    return [run_view(db, r) for r in rows]


def last_constraints(db: Session, event: Event) -> ConstraintSet:
    """직전 회차(같은 팀, 이 일정보다 앞선 일정)의 마지막 run 제약."""
    prev = db.scalar(
        select(AssignmentRun).join(Event)
        .where(Event.team_id == event.team_id, Event.id != event.id, Event.event_date <= event.event_date)
        .options(selectinload(AssignmentRun.constraints))
        .order_by(Event.event_date.desc(), AssignmentRun.created_at.desc())
    )
    if prev is None:
        raise errors.NotFound("지난 일정의 팀 배정 기록이 없어요.")
    return constraints_of(prev)


def get_run(db: Session, run_id: int) -> AssignmentRun:
    return _load_run(db, run_id)


def _load_candidate(db: Session, candidate_id: int) -> AssignmentCandidate:
    # populate_existing: 슬롯의 squad_id 를 바꾼 뒤에도 식별 맵의 stale 컬렉션이 아니라 DB 상태를 다시 읽는다
    c = db.get(
        AssignmentCandidate, candidate_id,
        options=[selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots), selectinload(AssignmentCandidate.run).selectinload(AssignmentRun.constraints)],
        populate_existing=True,
    )
    if c is None:
        raise errors.NotFound("배정안을 찾을 수 없어요.")
    return c


def _guard_editable(cand: AssignmentCandidate) -> tuple[set[int], set[int], dict[int, AssignmentSlot]]:
    if cand.is_adopted:
        raise errors.AlreadyAdopted("확정된 후보안은 수정할 수 없어요. 재배정을 실행해 주세요.")
    locked = {c.player_id for c in cand.run.constraints if c.type == ConstraintType.LOCK}
    pinned = {c.player_id for c in cand.run.constraints if c.type == ConstraintType.PIN}
    slot_of: dict[int, AssignmentSlot] = {s.player_id: s for sq in cand.squads for s in sq.slots}
    return locked, pinned, slot_of


def _separate_group_of(cand: AssignmentCandidate) -> dict[int, int]:
    """player_id → 갈라놓기 group_no. 갈라놓은 사람은 한 명만 옮길 수 없고 같은 그룹끼리 맞교체만 된다."""
    return {c.player_id: c.group_no for c in cand.run.constraints if c.type == ConstraintType.SEPARATE}


def _lock_groups_of(cand: AssignmentCandidate) -> dict[int, set[int]]:
    groups: dict[int, set[int]] = defaultdict(set)
    for c in cand.run.constraints:
        if c.type == ConstraintType.LOCK:
            groups[c.group_no].add(c.player_id)
    return {pid: members for members in groups.values() for pid in members}


def exchange(db: Session, cand: AssignmentCandidate, exchanges: list[Exchange]) -> AssignmentCandidate:
    """그룹 단위 교환: a 쪽은 상대 팀으로, b 쪽은 a 팀으로. 한쪽이 비면 일방 이동.

    - 묶음(LOCK)에 속한 사람이 있으면 묶음 전체를 자동으로 포함한다 (묶음은 통째로만 움직인다).
    - 갈라놓기(SEPARATE)는 교환 뒤에도 서로 다른 팀이어야 한다 (짝을 반대편에 함께 넣으면 통과).
    - 사전 배치(PIN)는 옮길 수 없다. 각 팀에 최소 5명은 남아야 한다.
    """
    if cand.is_adopted:
        raise errors.AlreadyAdopted("확정된 후보안은 수정할 수 없어요. 재배정을 실행해 주세요.")
    pinned = {c.player_id for c in cand.run.constraints if c.type == ConstraintType.PIN}
    lock_of = _lock_groups_of(cand)
    sep = _separate_group_of(cand)
    slot_of: dict[int, AssignmentSlot] = {s.player_id: s for sq in cand.squads for s in sq.slots}
    name_of = {sq.id: sq.squad_name for sq in cand.squads}
    for ex in exchanges:
        a, b = set(ex.a_player_ids), set(ex.b_player_ids)
        if not a and not b:
            continue
        for side in (a, b):  # 묶음 자동 확장
            for pid in list(side):
                side |= lock_of.get(pid, set())
        for pid in a | b:
            if pid not in slot_of:
                raise errors.InvalidSwap("이 배정안에 없는 사람이에요.")
            if pid in pinned:
                raise errors.InvalidSwap("사전 배치된 사람은 옮길 수 없어요.")
        if a & b:
            raise errors.InvalidSwap("같은 사람이 양쪽에 들어 있어요.")
        sq_a = {slot_of[p].squad_id for p in a}
        sq_b = {slot_of[p].squad_id for p in b}
        if len(sq_a) > 1 or len(sq_b) > 1:
            raise errors.InvalidSwap("한쪽에는 같은 팀 사람만 넣을 수 있어요.")
        if sq_a and sq_b and sq_a == sq_b:
            raise errors.InvalidSwap("같은 팀 안에서는 교체할 필요가 없어요.")
        squad_ids = [sq.id for sq in sorted(cand.squads, key=lambda x: x.squad_no)]
        if len(squad_ids) != 2:
            raise errors.InvalidSwap("두 팀으로 나눈 배정에서만 옮길 수 있어요.")
        src_a = next(iter(sq_a)) if sq_a else next(i for i in squad_ids if i not in sq_b)
        src_b = next(iter(sq_b)) if sq_b else next(i for i in squad_ids if i != src_a)
        # 결과 편성 계산 후 검증
        new_sq = {pid: s.squad_id for pid, s in slot_of.items()}
        for pid in a:
            new_sq[pid] = src_b
        for pid in b:
            new_sq[pid] = src_a
        groups: dict[int, list[int]] = defaultdict(list)
        for pid, g in sep.items():
            if pid in new_sq:
                groups[g].append(pid)
        for members in groups.values():
            if len({new_sq[p] for p in members}) < len(members):
                raise errors.InvalidSwap("갈라놓기로 설정된 사람은 갈라놓은 상대와 함께 팀을 바꿔야 해요. 한 명만 옮기면 같은 팀이 돼요.")
        for sid in squad_ids:
            if sum(1 for v in new_sq.values() if v == sid) < MIN_SQUAD_SIZE:
                raise errors.InvalidSwap(f"{name_of[sid]} 팀에 최소 {MIN_SQUAD_SIZE}명은 남아야 해요.")
        for pid in a | b:
            slot_of[pid].squad_id = new_sq[pid]
            slot_of[pid].is_manual_override = True
    _reload_slots(db, cand)
    _recompute_candidate(db, cand)
    db.commit()
    return _load_candidate(db, cand.id)


def swap(db: Session, cand: AssignmentCandidate, swaps: list[SwapPair]) -> AssignmentCandidate:
    """두 선수 맞교체 — Exchange 1:1 로 위임 (묶음은 자동 확장)."""
    return exchange(db, cand, [Exchange(a_player_ids=[sw.player_id_a], b_player_ids=[sw.player_id_b]) for sw in swaps])


def move(db: Session, cand: AssignmentCandidate, moves: list[MovePlayer]) -> AssignmentCandidate:
    """한 명(또는 묶음)을 지정한 팀으로 일방 이동 — Exchange 한쪽 비움으로 위임."""
    squads = {sq.squad_no: sq for sq in cand.squads}
    slot_of = {s.player_id: s for sq in cand.squads for s in sq.slots}
    exs = []
    for mv in moves:
        target = squads.get(mv.to_squad_no)
        slot = slot_of.get(mv.player_id)
        if target is None or slot is None:
            raise errors.InvalidSwap("없는 팀이거나 이 배정안에 없는 사람이에요.")
        if slot.squad_id == target.id:
            raise errors.InvalidSwap("이미 그 팀에 있어요.")
        exs.append(Exchange(a_player_ids=[mv.player_id], b_player_ids=[]))
    return exchange(db, cand, exs)


def _reload_slots(db: Session, cand: AssignmentCandidate) -> None:
    """slot.squad_id 를 바꾼 뒤 squad.slots 컬렉션이 stale 이므로 DB 에서 다시 읽는다."""
    db.flush()
    for sq in cand.squads:
        db.expire(sq, ["slots"])
    db.expire(cand, ["squads"])


def reset_manual(db: Session, cand: AssignmentCandidate) -> AssignmentCandidate:
    """수동 수정을 모두 되돌려 알고리즘이 낸 원래 편성으로 복원한다."""
    if cand.is_adopted:
        raise errors.AlreadyAdopted("확정한 배정안은 고칠 수 없어요.")
    original = cand.metrics.get("original_squads") or {}
    if not original:
        raise errors.ValidationError("처음 배정 결과가 남아 있지 않아 되돌릴 수 없어요.")
    squads = {sq.squad_no: sq for sq in cand.squads}
    slot_of: dict[int, AssignmentSlot] = {s.player_id: s for sq in cand.squads for s in sq.slots}
    for no, ids in original.items():
        for pid in ids:
            if pid in slot_of:
                slot_of[pid].squad_id = squads[int(no)].id
                slot_of[pid].is_manual_override = False
    _reload_slots(db, cand)
    _recompute_candidate(db, cand, manual=False)
    db.commit()
    return _load_candidate(db, cand.id)


def _recompute_candidate(db: Session, cand: AssignmentCandidate, *, manual: bool = True) -> None:
    event = db.get(Event, cand.run.event_id)
    roster = build_roster(db, event)
    rmap = {r.id: r for r in roster}
    squads: list[list[RosterPlayer]] = []
    for sq in sorted(cand.squads, key=lambda x: x.squad_no):
        squads.append([rmap[s.player_id] for s in sq.slots if s.player_id in rmap])
    body = AssignmentRunRequest(team_count=cand.run.team_count, strategies=[cand.strategy], constraints=constraints_of(cand.run))
    prep = prepare(roster, body)
    # 현재 편성을 partition 형태로 재구성해 같은 채점 함수를 쓴다
    node_sq = {}
    for i, s in enumerate(squads):
        for r in s:
            node_sq[prep.node_of[r.id]] = i
    partition = tuple(node_sq.get(n, 0) for n in range(len(prep.supernodes)))
    sc = score_partition(prep, partition, _load_pref_pairs(db, list(rmap)), _load_recent_pairs(db, event))
    sc.squads = squads
    cand.total_score = Decimal(str(round(sc.total(STRATEGY_WEIGHTS[cand.strategy]), 3)))
    positions: dict[int, Position | None] = {}
    for i, sq in enumerate(sorted(cand.squads, key=lambda x: x.squad_no)):
        pos = assign_positions(squads[i])
        positions.update(pos)
        sq.avg_skill = Decimal(str(round(mean(r.skill for r in squads[i]) if squads[i] else 0.0, 1)))
        for s in sq.slots:
            s.assigned_position = pos.get(s.player_id)
    original = cand.metrics.get("original_squads")
    cand.metrics = {**metrics_of(sc), "player_explanation": explain_player(sc, positions), "manually_edited": manual, "original_squads": original}
    cand.explanation = explain_manager(sc, cand.strategy, prep) + ("\n(매니저가 직접 수정한 편성이에요)" if manual else "")


def adopt(db: Session, cand: AssignmentCandidate) -> AssignmentCandidate:
    """후보안 확정 → 플레이어 공개. 이 회차의 지난 실행은 여기서 지운다.

    한 회차에 남는 배정 기록은 **확정한 실행 하나**뿐이다. 그 안의 후보안 3개는 지우지 않는다 —
    같은 결정의 비교 대상이고, 결과 화면이 확정 뒤에도 세 안을 그대로 보여 준다. 남은 run 의
    `roster_snapshot`·제약 덕분에 실력값이 바뀐 뒤에도 "그때 왜 이렇게 나눴는가" 를 설명할 수 있다.
    확정 전에는 지우지 않으므로, 재배정을 돌려 보는 동안에도 플레이어에게는 직전 확정안이 계속 보인다.
    """
    run_row = cand.run
    already = [c for c in run_row.candidates if c.is_adopted and c.id != cand.id]
    if already:
        raise errors.AlreadyAdopted()
    cand.is_adopted = True
    event = db.get(Event, run_row.event_id)
    if event.status == EventStatus.OPEN:
        event.status = EventStatus.CLOSED
    db.flush()
    _prune_history(db, run_row)
    db.commit()
    return _load_candidate(db, cand.id)


def _prune_history(db: Session, run_row: AssignmentRun) -> None:
    """확정한 실행만 남기고 이 회차의 지난 실행(재배정 전 결과)을 지운다."""
    for other in db.scalars(
        select(AssignmentRun).where(AssignmentRun.event_id == run_row.event_id, AssignmentRun.id != run_row.id)
    ).all():
        db.delete(other)
    db.flush()


def adopted_candidate(db: Session, event: Event) -> AssignmentCandidate | None:
    return db.scalar(
        select(AssignmentCandidate).join(AssignmentRun).where(AssignmentRun.event_id == event.id, AssignmentCandidate.is_adopted.is_(True))
        .options(selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots), selectinload(AssignmentCandidate.run))
        .order_by(AssignmentRun.created_at.desc())
    )


def adopted_view(db: Session, event: Event, me: Player) -> AdoptedAssignment:
    cand = adopted_candidate(db, event)
    if cand is None:
        raise errors.NotAdoptedYet()
    mask = me.role != TeamRole.MANAGER
    squads = squad_views(db, cand, mask=mask)
    my_sq, my_pos = None, None
    for sq in squads:
        if me.id in sq.assigned_positions:
            my_sq = sq.squad_no
            my_pos = sq.assigned_positions[me.id]
    return AdoptedAssignment(
        run_id=cand.run_id, candidate_id=cand.id, strategy=cand.strategy, squads=squads,
        explanation=cand.metrics.get("player_explanation") if mask else cand.explanation,
        my_squad_no=my_sq, my_player_id=me.id if my_sq is not None else None,
        my_assigned_position=my_pos.value if isinstance(my_pos, Position) else my_pos,
        adopted_at=cand.run.created_at if isinstance(cand.run.created_at, datetime) else None,
        skill_spread=cand.metrics.get("skill_spread"), total_score=float(cand.total_score) if cand.total_score is not None else None,
    )
