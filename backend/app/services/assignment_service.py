"""팀 배정 엔진 (설계서 9.5 ~ 9.7절 · F5 · F6 · F7 · F15 · F16).

흐름 (9.5절)
  1. 입력: 참석 확정자(회원+게스트), 팀 수 T, 회차별 제약(LOCK / SEPARATE / PIN)
  2. 실현가능성 사전 검사 → 실패면 422 + details (9.6절 표)
  3. PIN 은 그 팀에 고정, LOCK 은 Union-Find 로 **슈퍼노드** 로 축약 (제약 위반이 원천적으로 불가능)
  4. 2팀 · 12~16명 규모는 **완전 탐색** (조합 ≤ 수천 개, 9.7절) — 슈퍼노드 부분집합을 전부 평가.
     3팀(참석 16명 이상, 21명이면 7·7·7)은 조합이 수천만 개라 **지역 탐색** — 여러 번 새로 출발하는 탐욕 초기해에서
     맞바꾸기·옮기기 이웃을 한꺼번에(행렬로) 채점해 가장 좋은 쪽으로 옮기기를 더 나아지지 않을 때까지 되풀이한다
  5. 하드 제약: 각 팀에 1번(PG) 가능자 ≥ 1, 5번(PF/C) 가능자 ≥ 1. 만족하는 해가 없으면 경고 후 완화
  6. 목적함수 J 를 전략 3종 가중치로 각각 최소화 → 후보안 3개 (서로 다른 편성을 보장)
  7. 규칙 기반 설명 생성 (매니저용 수치 / 플레이어용 문장)

목적함수 (9.5절 7단계)
  J = w_skill·(팀 평균 실력 차)  + w_position·(포지션 커버리지 결손)
    + w_pref·(−팀 내 선호 조합)   + w_role·(선호 포지션 미충족)
    + w_fair·(최근 회차 같은 팀 반복) + w_guest·(게스트 편중)

2팀 · 3팀을 지원한다 (13.1절 Q4 — 참석이 많은 날 7명씩 3팀). 4팀 이상은 422 로 안내한다.
"""

from __future__ import annotations

import itertools
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from statistics import mean, pstdev

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, selectinload

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
    Quarter,
    User,
)
from app.models.enums import (
    DEFAULT_SQUAD_NAMES,
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
from app.services.player_service import PLAYER_LOAD, to_card

SQUAD_NAMES = list(DEFAULT_SQUAD_NAMES)  # 13.1절 Q6 기본값 — 1 블랙 · 2 화이트 · 3 레드
MAX_SUPERNODES = 18  # 2팀 완전 탐색 상한. 팀 인원을 고르게 맞추는 분할만 세므로 18개면 약 2만 개, 실측 0.09초 (2026-10, 행렬 채점). 넘으면 막지 않고 지역 탐색으로 푼다
HARD_PENALTY = 10.0
MIN_SQUAD = 5  # 팀마다 코트에 설 5명은 있어야 한다 (배정 · 수동 수정 모두)
MAX_TEAMS = 3
LS_RESTARTS = 6  # 3팀 지역 탐색: 전략마다 새로 출발하는 횟수
LS_RESTARTS_2 = 12  # 2팀(18명 초과)은 이웃이 맞바꾸기뿐이라 국소 최적에 잘 빠진다 — 두 배로 (16명 60건 모두 완전 탐색 최적, 24명 0.13초)
LS_PATIENCE = 8  # 흔들기가 이만큼 연달아 나아지지 않으면 멈춘다 (시간 대부분이 헛도는 흔들기였다)
LS_KICKS = 25  # 국소 최적에 빠지면 두 번 무작위로 맞바꿔 흔든 뒤 다시 내려가 보는 횟수 (더 나으면 옮겨 간다)
LS_SEED = 20260929  # 같은 입력이면 같은 결과가 나오도록 고정

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
        .options(*PLAYER_LOAD)
        .order_by(Player.display_name)
    ).scalars().all()
    return _roster_from(rows)


def _skill_of(p: Player) -> tuple[float | None, bool]:
    """(실력값, 믿을 만한가). 경기 실력 > 사전값. 게스트처럼 신뢰도 0 이면 모르는 값으로 본다."""
    prof = p.profile
    v = prof.skill_overall if prof and prof.skill_overall is not None else (prof.prior_overall if prof else None)
    return (float(v) if v is not None else None), v is not None and not (prof and prof.skill_confidence == 0)


def _roster_from(rows: Sequence[Player]) -> list[RosterPlayer]:
    """참가자 → 배정 입력. 실력을 모르는 사람은 이 명단의 평균으로 둔다. `rows` 는 이름순이어야 한다."""
    skills = [(p, *_skill_of(p)) for p in rows]
    known = [v for _, v, ok in skills if ok and v is not None]
    default = mean(known) if known else 0.0
    roster = []
    for p, v, is_known in skills:
        playable = {pp.position for pp in p.positions if pp.can_play}
        ranked = sorted((pp for pp in p.positions if pp.can_play and pp.preference_rank), key=lambda x: x.preference_rank)
        roster.append(
            RosterPlayer(
                player=p, skill=v if is_known and v is not None else default, known=is_known, playable=playable,
                primary=ranked[0].position if ranked else None, pref_rank={pp.position: pp.preference_rank for pp in ranked},
            )
        )
    return roster


def _squad_sizes(n: int, t: int) -> list[int]:
    """N명을 T팀으로 최대한 고르게. 13명 2팀 → [7, 6]."""
    base, extra = divmod(n, t)
    return [base + (1 if i < extra else 0) for i in range(t)]


def _size_levels(n: int) -> list[list[int]]:
    """2팀일 때 첫 팀(블랙) 인원 후보를 '고른 정도' 순으로 묶는다. 16명 → [[8], [7, 9], [6, 10], [5, 11]].

    배정은 가장 고른 단계부터 해를 찾고, 묶음 때문에 그 단계에 해가 없을 때만 다음 단계(한 명씩 더 벌어진 인원)로
    넘어간다 — 게스트 여럿을 한 팀으로 묶어 9:7 로 뛰려는 경우를 막지 않기 위해서. 어느 팀이든 5명 밑으로는 내려가지 않는다.
    """
    xs = [x for x in range(MIN_SQUAD, n - MIN_SQUAD + 1)]
    gaps = sorted({abs(2 * x - n) for x in xs})
    return [[x for x in xs if abs(2 * x - n) == g] for g in gaps]


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
    skill_sd: float = 0.0  # 명단 전체 실력 표준편차 — 분할 수천 개를 채점할 때 매번 다시 구하지 않는다


def prepare(roster: list[RosterPlayer], body: AssignmentRunRequest) -> Prepared:
    """제약을 검증하고 슈퍼노드로 축약한다. 위반은 violations 에 모아 돌려준다 (예외를 던지지 않는다)."""
    rmap = {r.id: r for r in roster}
    t = body.team_count
    n = len(roster)
    v: list[ConstraintViolation] = []
    warnings: list[str] = []
    c = body.constraints

    if t not in (2, MAX_TEAMS):
        v.append(ConstraintViolation(code="VALIDATION_ERROR", message="2팀 또는 3팀으로만 나눌 수 있어요."))
    if n < t * 5:
        v.append(ConstraintViolation(code="NOT_ENOUGH_PLAYERS", message=f"{t}팀을 만들려면 최소 {t * 5}명이 필요해요 (현재 {n}명)"))

    # 알 수 없는 참가자
    referenced = {pid for g in c.lock_groups + c.separate_groups for pid in g} | {p.player_id for p in c.pins}
    unknown = sorted(pid for pid in referenced if pid not in rmap)
    if unknown:
        v.append(ConstraintViolation(code="PLAYER_NOT_IN_TEAM", message="참석 확정자가 아닌 인원이 제약에 들어 있어요.", player_ids=unknown))

    sizes = _squad_sizes(n, t) if t > 0 else []
    # 한 팀이 가질 수 있는 최대 인원 = 상대 팀에 5명을 남기는 선. 고르게 못 나누면 인원을 벌려서라도 묶음을 지킨다
    capacity = n - MIN_SQUAD * (t - 1) if t > 1 else n

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
            v.append(ConstraintViolation(code="LOCK_GROUP_TOO_LARGE", message=f"묶음 그룹이 {len(ids)}명이라 상대 팀에 {MIN_SQUAD}명이 남지 않아요 (한 팀 최대 {capacity}명).", player_ids=ids, group_no=i))

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
        if sizes and cnt > capacity:
            v.append(ConstraintViolation(code="SQUAD_OVERFLOW", message=f"{SQUAD_NAMES[sq]} 팀에 {cnt}명을 미리 배치하면 상대 팀에 {MIN_SQUAD}명이 남지 않아요 (한 팀 최대 {capacity}명)."))
    # SEPARATE 인데 같은 팀에 PIN
    for a, b in sep_pairs:
        if a in pins and b in pins and pins[a] == pins[b]:
            v.append(ConstraintViolation(code="SEPARATE_INFEASIBLE", message="갈라놓기로 지정한 두 사람이 같은 팀에 배치됐어요.", player_ids=supernodes[a] + supernodes[b]))


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
    """슈퍼노드를 두 팀으로 나누는 모든 방법을 (squad index per node) 튜플로 낸다. PIN·SEPARATE 를 지킨다.

    인원은 가장 고른 단계(16명이면 8:8)의 해만 낸다. 묶음·사전 배치 때문에 그 단계에 해가 하나도 없을 때만
    한 명씩 더 벌어진 단계(9:7 → 10:6 …, 팀마다 5명 이상)로 넘어간다. 해를 찾은 단계의 인원을 `prep.sizes` 에 적는다.
    """
    nodes = list(range(len(prep.supernodes)))
    free = [i for i in nodes if i not in prep.pins]
    size = [len(prep.supernodes[i]) for i in nodes]
    n = sum(size)
    pinned0 = sum(size[i] for i, sq in prep.pins.items() if sq == 0)
    # 대칭 제거: PIN 이 없으면 첫 자유 노드는 항상 팀 0 (블랙/화이트 이름만 바뀌는 중복 해 제거).
    # 팀 0 인원 후보를 단계마다 둘 다(9 와 7) 보므로 앵커가 큰 팀·작은 팀에 있는 경우를 모두 센다
    anchor = free[0] if free and not prep.pins else None
    sizes_free = sorted(size[i] for i in free)
    for level in _size_levels(n):
        found = False
        for team0 in level:
            need0 = team0 - pinned0
            if need0 < 0:
                continue
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
                    if not found:
                        found = True
                        prep.sizes = [team0, n - team0]
                    yield tuple(assign[i] for i in nodes)
        if found:
            return


# ---------------------------------------------------------------------------
# 목적함수
# ---------------------------------------------------------------------------


def _squads_of(prep: Prepared, partition: tuple[int, ...]) -> list[list[RosterPlayer]]:
    squads: list[list[RosterPlayer]] = [[] for _ in range(prep.team_count)]
    for node, sq in enumerate(partition):
        for pid in prep.supernodes[node]:
            squads[sq].append(prep.roster[pid])
    return squads


@dataclass
class Scored:
    partition: tuple[int, ...]
    terms: dict[str, float]
    hard_ok: bool
    # 팀별 명단은 처음 읽을 때 만든다 — 분할 수천 개를 채점해도 실제로 쓰는 건 후보안 3개뿐이다
    _squads: list[list[RosterPlayer]] | None = field(default=None, repr=False)
    _prep: Prepared | None = field(default=None, repr=False)

    @property
    def squads(self) -> list[list[RosterPlayer]]:
        if self._squads is None:
            if self._prep is None:
                raise RuntimeError("Scored 에 명단도 준비 정보도 없어요")
            self._squads = _squads_of(self._prep, self.partition)
        return self._squads

    @squads.setter
    def squads(self, value: list[list[RosterPlayer]]) -> None:
        self._squads = value  # 수동 교체(exchange)는 채점 뒤 명단을 바꿔 넣는다

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
    """최근 회차에서 같은 팀이었던 쌍 (w_fair). 회차 수와 무관하게 쿼리 두 번."""
    prev_ids = list(db.scalars(
        select(Event.id).where(Event.team_id == event.team_id, Event.id != event.id, Event.event_date <= event.event_date)
        .order_by(Event.event_date.desc(), Event.id.desc()).limit(limit_events)
    ).all())
    if not prev_ids:
        return set()
    rows = db.execute(
        select(AssignmentSquad.id, AssignmentSlot.player_id)
        .join(AssignmentSlot, AssignmentSlot.squad_id == AssignmentSquad.id)
        .join(AssignmentCandidate, AssignmentCandidate.id == AssignmentSquad.candidate_id)
        .join(AssignmentRun, AssignmentRun.id == AssignmentCandidate.run_id)
        .where(AssignmentRun.event_id.in_(prev_ids), AssignmentCandidate.is_adopted.is_(True))
    ).all()
    by_squad: dict[int, list[int]] = defaultdict(list)
    for squad_id, pid in rows:
        by_squad[squad_id].append(pid)
    pairs: set[tuple[int, int]] = set()
    for ids in by_squad.values():
        pairs.update(itertools.combinations(sorted(ids), 2))
    return pairs


def _skill_sd(prep: Prepared) -> float:
    skills = [r.skill for r in prep.roster.values()]
    return pstdev(skills) if len(skills) > 1 else 0.0


def score_partition(prep: Prepared, partition: tuple[int, ...], pref_pairs: dict, recent_pairs: set) -> Scored:
    """분할 하나를 채점한다. 읽기 쉬운 기준 구현 — 완전 탐색은 같은 식을 행렬로 푸는 `score_partitions` 를 쓴다."""
    squads = _squads_of(prep, partition)
    if not prep.skill_sd:
        prep.skill_sd = _skill_sd(prep)
    means = [sum(r.skill for r in s) / len(s) if s else 0.0 for s in squads]
    # skill: 팀 평균 차이를 실력 표준편차로 정규화 (0 = 완전 균형)
    skill = (max(means) - min(means)) / max(prep.skill_sd, 0.5)

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
    # 포지션 분포 불균형: 포지션마다 가장 많은 팀과 가장 적은 팀의 차이 (2팀이면 |블랙 − 화이트|)
    imbalance = sum(max(c[pos] for c in counts) - min(c[pos] for c in counts) for pos in Position) / max(1, len(prep.roster))
    position = missing + imbalance

    # role: 같은 팀에서 같은 주 포지션이 과다 (정원 5 기준 포지션당 1자리, 팀 인원이 많으면 2자리)
    role = 0.0
    for s, c in zip(squads, counts, strict=True):
        slots = 1 if len(s) <= 5 else 2
        role += sum(max(0, cnt - slots) for cnt in c.values())
    role /= max(1, len(prep.roster))

    # pref: 팀 내 선호 조합 합 (클수록 좋음 → 음수로) · fair: 최근 회차 같은 팀 반복 쌍 비율
    # 둘 다 같은 팀 쌍을 훑으므로 한 번에 돈다. 자료가 없으면 아예 훑지 않는다
    pref = 0.0
    repeats = 0
    if pref_pairs or recent_pairs:
        for s in squads:
            ids = sorted(r.id for r in s)
            for pair in itertools.combinations(ids, 2):
                pref += pref_pairs.get(pair, 0.0)
                if pair in recent_pairs:
                    repeats += 1
    pref = -pref / max(1, len(prep.roster) / 2)
    fair = repeats / max(1, len(recent_pairs)) if recent_pairs else 0.0

    # guest: 게스트(특히 데이터 없는) 편중
    gcounts = [sum(1 for r in s if r.is_guest) for s in squads]
    guest = (max(gcounts) - min(gcounts)) / max(1, sum(gcounts)) if sum(gcounts) else 0.0

    return Scored(partition=partition, _squads=squads, terms={"skill": skill, "position": position, "pref": pref, "role": role, "fair": fair, "guest": guest, "means": means}, hard_ok=hard_ok)


@dataclass
class _NodeStats:
    """슈퍼노드별 값과 노드 쌍 행렬 — 분할 여러 개를 한 번에 채점할 때 쓴다. 명단 · 선호 · 최근 쌍마다 한 번 만든다."""

    size: np.ndarray
    skill_sum: np.ndarray
    handle: np.ndarray
    big: np.ndarray
    guest: np.ndarray
    prim: np.ndarray  # (노드, 포지션) 주 포지션 인원
    pref_u: np.ndarray  # (노드, 노드) i<j 쌍 사이 선호 합
    rec_u: np.ndarray  # (노드, 노드) i<j 쌍 사이 최근 같은 팀 쌍 수
    pref_const: float  # 노드 안의 쌍 — 어느 분할에서도 같은 팀이라 상수
    rec_const: int
    has_pairs: bool


def _node_stats(prep: Prepared, pref_pairs: dict, recent_pairs: set) -> _NodeStats:
    n_nodes = len(prep.supernodes)
    positions = list(Position)
    pos_idx = {pos: i for i, pos in enumerate(positions)}
    size = np.zeros(n_nodes)
    skill_sum = np.zeros(n_nodes)
    handle = np.zeros(n_nodes)
    big = np.zeros(n_nodes)
    guest = np.zeros(n_nodes)
    prim = np.zeros((n_nodes, len(positions)))
    members: list[list[int]] = []
    for i, ids in enumerate(prep.supernodes):
        rs = [prep.roster[pid] for pid in ids]
        members.append(list(ids))
        size[i] = len(rs)
        skill_sum[i] = sum(r.skill for r in rs)
        handle[i] = float(any(r.can_handle for r in rs))
        big[i] = float(any(r.can_big for r in rs))
        guest[i] = sum(1 for r in rs if r.is_guest)
        for r in rs:
            if r.primary:
                prim[i, pos_idx[r.primary]] += 1
    pref_u = np.zeros((n_nodes, n_nodes))
    rec_u = np.zeros((n_nodes, n_nodes))
    pref_const = 0.0
    rec_const = 0
    has_pairs = bool(pref_pairs or recent_pairs)
    if has_pairs:
        def pair_terms(ids_a: list[int], ids_b: list[int] | None) -> tuple[float, int]:
            pairs = itertools.combinations(sorted(ids_a), 2) if ids_b is None else ((min(a, b), max(a, b)) for a in ids_a for b in ids_b)
            pv, rc = 0.0, 0
            for key in pairs:
                pv += pref_pairs.get(key, 0.0)
                if key in recent_pairs:
                    rc += 1
            return pv, rc

        for i in range(n_nodes):
            pv, rc = pair_terms(members[i], None)
            pref_const += pv
            rec_const += rc
            for j in range(i + 1, n_nodes):
                pref_u[i, j], rec_u[i, j] = pair_terms(members[i], members[j])
    return _NodeStats(size, skill_sum, handle, big, guest, prim, pref_u, rec_u, pref_const, rec_const, has_pairs)


def _terms_matrix(prep: Prepared, st: _NodeStats, P: np.ndarray, n_recent: int) -> dict[str, np.ndarray]:
    """분할 행렬 P(분할 × 노드, 값 = 팀 번호 0..T-1)의 항을 한꺼번에 계산한다. `score_partition` 과 같은 식이다.

    팀 s 의 소속 여부 M_s = (P == s) 로 인원·실력 합·포지션 수를 M_s·(노드별 값) 으로, 같은 팀 쌍의 선호·반복 합은
    노드 쌍 행렬 U 로 M_sᵀ U M_s 를 팀마다 더해 얻는다. 파이썬 루프 대신 행렬 연산이라 수천 개도 수 ms 다.
    """
    t = prep.team_count
    n_roster = max(1, len(prep.roster))
    Ms = [(P == s).astype(float) for s in range(t)]
    sizes = np.stack([M @ st.size for M in Ms])  # (T, m)
    sums = np.stack([M @ st.skill_sum for M in Ms])
    means = np.where(sizes > 0, sums / np.maximum(sizes, 1), 0.0)
    skill = (means.max(axis=0) - means.min(axis=0)) / max(prep.skill_sd, 0.5)
    missing = sum(((M @ st.handle) == 0).astype(int) + ((M @ st.big) == 0).astype(int) for M in Ms)
    counts = np.stack([M @ st.prim for M in Ms])  # (T, m, 포지션)
    imbalance = (counts.max(axis=0) - counts.min(axis=0)).sum(axis=1) / n_roster
    slots = np.where(sizes <= 5, 1, 2)[:, :, None]
    role = np.maximum(0, counts - slots).sum(axis=(0, 2)) / n_roster
    m = P.shape[0]
    if st.has_pairs:
        # 같은 팀 쌍 합 = Σ_s rowsum((M_s U) ⊙ M_s) — einsum 보다 행렬곱이 열 배 넘게 빠르다
        pref_sum = sum(((M @ st.pref_u) * M).sum(axis=1) for M in Ms) + st.pref_const
        repeats = sum(((M @ st.rec_u) * M).sum(axis=1) for M in Ms) + st.rec_const
    else:
        pref_sum = np.zeros(m)
        repeats = np.zeros(m)
    pref = -pref_sum / max(1, n_roster / 2)
    fair = repeats / max(1, n_recent) if n_recent else np.zeros(m)
    g = np.stack([M @ st.guest for M in Ms])
    gsum = g.sum(axis=0)
    guest = np.where(gsum > 0, (g.max(axis=0) - g.min(axis=0)) / np.maximum(gsum, 1), 0.0)
    return {"skill": skill, "position": missing + imbalance, "pref": pref, "role": role, "fair": fair, "guest": guest, "missing": missing, "means": means}


def _totals(terms: dict[str, np.ndarray], w: dict[str, float]) -> np.ndarray:
    j = (w["skill"] * terms["skill"] + w["position"] * terms["position"] + w["pref"] * terms["pref"] + w["role"] * terms["role"]
         + W_FAIR * terms["fair"] + W_GUEST * terms["guest"])
    return j + np.where(terms["missing"] > 0, HARD_PENALTY, 0.0)


def score_partitions(prep: Prepared, partitions: list[tuple[int, ...]], pref_pairs: dict, recent_pairs: set, stats: _NodeStats | None = None) -> list[Scored]:
    """분할 전부를 한 번에 채점한다 — `score_partition` 과 같은 값을 내지만 파이썬 루프 대신 행렬 연산이다 (2팀 · 3팀)."""
    if not partitions:
        return []
    if not prep.skill_sd:
        prep.skill_sd = _skill_sd(prep)
    st = stats or _node_stats(prep, pref_pairs, recent_pairs)
    tm = _terms_matrix(prep, st, np.asarray(partitions, dtype=int), len(recent_pairs))
    out = []
    for k, part in enumerate(partitions):
        out.append(Scored(
            partition=part,
            terms={"skill": float(tm["skill"][k]), "position": float(tm["position"][k]), "pref": float(tm["pref"][k]), "role": float(tm["role"][k]),
                   "fair": float(tm["fair"][k]), "guest": float(tm["guest"][k]), "means": [float(x) for x in tm["means"][:, k]]},
            hard_ok=bool(tm["missing"][k] == 0), _prep=prep,
        ))
    return out


# ---------------------------------------------------------------------------
# 지역 탐색 (3팀)
# ---------------------------------------------------------------------------


def _sep_of(prep: Prepared) -> dict[int, set[int]]:
    out: dict[int, set[int]] = defaultdict(set)
    for a, b in prep.separate_pairs:
        out[a].add(b)
        out[b].add(a)
    return out


def _construct(prep: Prepared, rng: random.Random, sep_of: dict[int, set[int]]) -> tuple[int, ...] | None:
    """탐욕 초기해: 큰 묶음·센 사람부터, 갈라놓기를 지키며 정원이 남는 팀 중 실력 합이 가장 낮은 팀에 넣는다.
    정원에 맞는 팀이 없으면(묶음이 커서) 가장 적은 팀에 넣어 인원이 벌어지는 것을 허용한다. 5명 못 채우는 팀이 생기면 None."""
    t = prep.team_count
    size = [len(ids) for ids in prep.supernodes]
    skill = [sum(prep.roster[p].skill for p in ids) for ids in prep.supernodes]
    target = _squad_sizes(sum(size), t)
    rng.shuffle(target)
    assign: dict[int, int] = dict(prep.pins)
    load = [0] * t
    ssum = [0.0] * t
    for node, sq in prep.pins.items():
        load[sq] += size[node]
        ssum[sq] += skill[node]
    noise = max(prep.skill_sd, 0.5) * 0.35
    free = sorted((i for i in range(len(size)) if i not in prep.pins), key=lambda i: (-size[i], -(skill[i] / size[i]) + rng.uniform(-noise, noise)))
    for i in free:
        ok = [s for s in range(t) if all(assign.get(o) != s for o in sep_of.get(i, ()))]
        if not ok:
            return None
        fit = [s for s in ok if load[s] + size[i] <= target[s]]
        s = min(fit, key=lambda x: (ssum[x], load[x], rng.random())) if fit else min(ok, key=lambda x: (load[x], rng.random()))
        assign[i] = s
        load[s] += size[i]
        ssum[s] += skill[i]
    if min(load) < MIN_SQUAD:
        return None
    return tuple(assign[i] for i in range(len(size)))


def _spread(prep: Prepared, part: tuple[int, ...]) -> int:
    sizes = [sum(len(prep.supernodes[i]) for i, s in enumerate(part) if s == sq) for sq in range(prep.team_count)]
    return max(sizes) - min(sizes)


def _good_start(prep: Prepared, rng: random.Random, sep_of: dict[int, set[int]], ideal_spread: int, tries: int = 30) -> tuple[int, ...] | None:
    """초기해 여러 개 중 인원이 가장 고른 것 — 갈라놓기 때문에 탐욕이 가끔 인원을 벌리므로, 고르게 되면 바로 쓴다."""
    best: tuple[int, ...] | None = None
    for _ in range(tries):
        c = _construct(prep, rng, sep_of)
        if c is None:
            continue
        if _spread(prep, c) <= ideal_spread:
            return c
        if best is None or _spread(prep, c) < _spread(prep, best):
            best = c
    return best


def _canon(part: tuple[int, ...], pinned: bool) -> tuple[int, ...]:
    """사전 배치가 없으면 팀 이름만 바뀐 같은 편성을 하나로 — 처음 나온 순서로 팀 번호를 다시 매긴다."""
    if pinned:
        return part
    remap: dict[int, int] = {}
    return tuple(remap.setdefault(x, len(remap)) for x in part)


@dataclass
class _MoveIndex:
    """이웃을 만들 인덱스 — 자유 노드 쌍(맞바꾸기)과 (노드, 팀)(옮기기). 탐색 동안 바뀌지 않아 한 번만 만든다."""

    swap_a: np.ndarray
    swap_b: np.ndarray
    move_node: np.ndarray
    move_team: np.ndarray


def _move_index(free: list[int], t: int) -> _MoveIndex:
    pairs = [(a, b) for x, a in enumerate(free) for b in free[x + 1:]]
    moves = [(a, s) for a in free for s in range(t)]
    arr = lambda xs, k: np.array([p[k] for p in xs], dtype=int)
    return _MoveIndex(arr(pairs, 0), arr(pairs, 1), arr(moves, 0), arr(moves, 1))


def _neighbors(prep: Prepared, part: np.ndarray, mi: _MoveIndex, sep: np.ndarray, st: _NodeStats, max_spread: float) -> np.ndarray:
    """맞바꾸기(서로 다른 팀의 두 노드) · 옮기기(노드 하나를 다른 팀으로) 이웃 중 인원 · 갈라놓기 조건을 지키는 것.
    행을 하나씩 복사하지 않고 인덱스 배열로 한꺼번에 만든다 (예전 파이썬 루프의 절반 이상이던 시간)."""
    t = prep.team_count
    sw = part[mi.swap_a] != part[mi.swap_b]
    a, b = mi.swap_a[sw], mi.swap_b[sw]
    P1 = np.repeat(part[None, :], len(a), axis=0)
    r1 = np.arange(len(a))
    P1[r1, a], P1[r1, b] = part[b], part[a]
    mv = part[mi.move_node] != mi.move_team
    n, sq = mi.move_node[mv], mi.move_team[mv]
    P2 = np.repeat(part[None, :], len(n), axis=0)
    P2[np.arange(len(n)), n] = sq
    P = np.concatenate([P1, P2]) if len(P2) else P1
    if not len(P):
        return P
    sizes = np.stack([(P == s) @ st.size for s in range(t)])
    ok = (sizes.min(axis=0) >= MIN_SQUAD) & ((sizes.max(axis=0) - sizes.min(axis=0)) <= max_spread + 1e-9)
    if len(sep):
        ok &= (P[:, sep[:, 0]] != P[:, sep[:, 1]]).all(axis=1)
    return P[ok]


def search_partitions(prep: Prepared, pref_pairs: dict, recent_pairs: set, strategies: list[Strategy]) -> tuple[list[Scored], int]:
    """지역 탐색 — 3팀, 그리고 묶음 뒤 사람이 MAX_SUPERNODES 를 넘는 2팀. 전략마다 LS_RESTARTS 번 새로 출발해, 이웃 전부를 한 번에 채점하고 가장 좋은 이웃으로 옮기기를
    더 나아지지 않을 때까지 한다. 찾은 국소 최적해들(서로 다른 편성)을 돌려준다 — 후보안 3개가 서로 달라야 하므로.
    반환: (채점한 국소 최적해, 채점한 분할 수)."""
    if not prep.skill_sd:
        prep.skill_sd = _skill_sd(prep)
    st = _node_stats(prep, pref_pairs, recent_pairs)
    rng = random.Random(LS_SEED + len(prep.roster))
    sep_of = _sep_of(prep)
    sep = np.array(sorted(prep.separate_pairs), dtype=int).reshape(-1, 2)
    free = [i for i in range(len(prep.supernodes)) if i not in prep.pins]
    ideal = _squad_sizes(sum(len(x) for x in prep.supernodes), prep.team_count)
    ideal_spread = max(ideal) - min(ideal)
    mi = _move_index(free, prep.team_count)
    optima: dict[tuple[int, ...], tuple[int, ...]] = {}
    evaluated = 0
    n_recent = len(recent_pairs)

    def descend(part: np.ndarray, cur: float, w: dict[str, float], max_spread: float) -> tuple[np.ndarray, float]:
        nonlocal evaluated
        while True:
            P = _neighbors(prep, part, mi, sep, st, max_spread)
            if not len(P):
                return part, cur
            j = _totals(_terms_matrix(prep, st, P, n_recent), w)
            evaluated += len(P)
            k = int(np.argmin(j))
            if j[k] >= cur - 1e-9:
                return part, cur
            part, cur = P[k], float(j[k])

    for strategy in strategies:
        w = STRATEGY_WEIGHTS[strategy]
        for _ in range(LS_RESTARTS_2 if prep.team_count == 2 else LS_RESTARTS):
            start = _good_start(prep, rng, sep_of, ideal_spread)
            if start is None:
                break
            part = np.array(start, dtype=int)
            max_spread = max(ideal_spread, _spread(prep, start))  # 묶음 때문에 벌어진 인원보다 더 벌리지는 않는다
            part, cur = descend(part, float(_totals(_terms_matrix(prep, st, part[None, :], n_recent), w)[0]), w, max_spread)
            optima.setdefault(_canon(tuple(int(x) for x in part), bool(prep.pins)), ())
            # 흔들기: 서로 다른 팀의 두 노드를 두 번 맞바꾼 뒤 다시 내려간다. 더 나으면 거기서 이어 간다
            stale = 0
            for _ in range(LS_KICKS):
                if stale >= LS_PATIENCE:  # 연달아 나아지지 않으면 이 출발점은 여기까지
                    break
                stale += 1
                trial = part.copy()
                for _ in range(2):
                    x, y = rng.sample(free, 2) if len(free) >= 2 else (free[0], free[0])
                    if trial[x] != trial[y] and st.size[x] == st.size[y]:
                        trial[x], trial[y] = trial[y], trial[x]
                if len(sep) and not (trial[sep[:, 0]] != trial[sep[:, 1]]).all():
                    continue
                t_cur = float(_totals(_terms_matrix(prep, st, trial[None, :], n_recent), w)[0])
                trial, t_cur = descend(trial, t_cur, w, max_spread)
                optima.setdefault(_canon(tuple(int(x) for x in trial), bool(prep.pins)), ())
                if t_cur < cur - 1e-9:
                    part, cur, stale = trial, t_cur, 0
    parts = list(optima)
    if parts:
        sizes = [sum(len(prep.supernodes[i]) for i, s in enumerate(parts[0]) if s == sq) for sq in range(prep.team_count)]
        prep.sizes = sizes
    return score_partitions(prep, parts, pref_pairs, recent_pairs, st), evaluated + len(parts)


def first_partition(prep: Prepared) -> tuple[int, ...] | None:
    """조건을 지키는 편성이 하나라도 있는가 — 완전 탐색하는 2팀은 그 첫 해, 그 밖은 탐욕 초기해를 여러 번 시도."""
    if prep.team_count == 2 and len(prep.supernodes) <= MAX_SUPERNODES:
        return next(enumerate_partitions(prep), None)
    ideal = _squad_sizes(sum(len(x) for x in prep.supernodes), prep.team_count)
    c = _good_start(prep, random.Random(LS_SEED), _sep_of(prep), max(ideal) - min(ideal), tries=60)
    if c is not None:
        prep.sizes = [sum(len(prep.supernodes[i]) for i, s in enumerate(c) if s == sq) for sq in range(prep.team_count)]
    return c


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
        "team_count": len(sc.squads),
        "guest_count_per_squad": [sum(1 for r in s if r.is_guest) for s in sc.squads],
        "unknown_skill_per_squad": [sum(1 for r in s if not r.known) for s in sc.squads],
        "terms": {k: round(v, 3) for k, v in sc.terms.items() if k != "means"},
        "hard_constraints_met": sc.hard_ok,
    }


def explain_manager(sc: Scored, strategy: Strategy, prep: Prepared) -> str:
    means = sc.terms["means"]
    names = SQUAD_NAMES
    gap = max(means) - min(means)
    three = len(means) >= 3
    vs = "가장 강한 팀과 가장 약한 팀이" if three else "두 팀이"
    lines = [
        f"[{STRATEGY_LABEL[strategy]}] " + " · ".join(f"{names[i]} {len(sc.squads[i])}명" for i in range(len(means)))
        + f" — {vs} 붙으면 한 쿼터에 약 {gap:.2f}점 차가 날 것으로 예상돼요 (0에 가까울수록 균형)."  # 결과 화면 상단 카드(skill_spread 소수 둘째 자리)와 같은 자릿수
    ]
    if sc.hard_ok:
        lines.append(f"{'세 팀' if three else '양 팀'} 모두 1번(볼 운반)·5번(골밑) 가능 인원을 확보했어요.")
    else:
        lines.append("⚠ 오늘 인원으로는 어느 팀에 볼 운반이나 골밑을 맡을 사람이 없어요.")
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
    lines = [f"실력이 비슷하도록 {_TEAMS_WORD.get(len(sc.squads), '팀')}을 나눴어요."]
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
    return _validate_prepared(prepare(build_roster(db, event), body))


def _validate_prepared(prep: Prepared) -> ValidateResult:
    if prep.violations:
        return ValidateResult(feasible=False, violations=prep.violations, warnings=prep.warnings)
    # 분할 가능성: 해가 하나라도 있는지 (찾으면 prep.sizes 가 실제 인원으로 바뀐다)
    ideal = list(prep.sizes)
    if first_partition(prep) is None:
        code = "SEPARATE_INFEASIBLE" if prep.separate_pairs else "LOCK_PARTITION_INFEASIBLE"
        msg = "갈라놓기 제약을 모두 만족하는 팀 구성이 없어요." if prep.separate_pairs else _partition_msg(prep)
        return ValidateResult(feasible=False, violations=[ConstraintViolation(code=code, message=msg)], warnings=prep.warnings)
    _warn_uneven(prep, ideal)
    return ValidateResult(feasible=True, warnings=prep.warnings)


def _ro(n: int) -> str:
    """숫자 뒤 조사 '로/으로' — 끝자리를 읽는 소리 기준 (0 영·3 삼·6 육 은 받침이 있어 '으로')."""
    return "으로" if n % 10 in (0, 3, 6) else "로"


def _warn_uneven(prep: Prepared, ideal: list[int]) -> None:
    """묶음 때문에 고르게 못 나눴으면 알려 준다 (차단 아님). 팀마다 5명 이상이면 비율은 제한하지 않는다."""
    if sorted(prep.sizes) != sorted(ideal):
        ordered = sorted(prep.sizes, reverse=True)
        small = ordered[-1]
        note = f"묶음을 지키려고 {_TEAMS_WORD.get(len(ordered), '팀')} 인원을 {':'.join(map(str, ordered))}{_ro(small)} 나눴어요"
        if note not in prep.warnings:
            prep.warnings.append(note)


_TEAMS_WORD = {2: "두 팀", 3: "세 팀"}


def _partition_msg(prep: Prepared) -> str:
    sizes = sorted((len(ids) for ids in prep.supernodes if len(ids) > 1), reverse=True)
    return f"{'명 그룹과 '.join(str(x) for x in sizes)}명 그룹으로는 {_TEAMS_WORD.get(prep.team_count, '팀')}을 각각 {MIN_SQUAD}명 이상으로 나눌 수 없어요."


def _raise_violations(vr: ValidateResult) -> None:
    first = vr.violations[0]
    cls = {
        "NOT_ENOUGH_PLAYERS": errors.NotEnoughPlayers, "LOCK_GROUP_TOO_LARGE": errors.LockGroupTooLarge,
        "CONSTRAINT_CONFLICT": errors.ConstraintConflict, "SEPARATE_INFEASIBLE": errors.SeparateInfeasible,
        "LOCK_PARTITION_INFEASIBLE": errors.LockPartitionInfeasible, "SQUAD_OVERFLOW": errors.SquadOverflow,
        "PLAYER_NOT_IN_TEAM": errors.PlayerNotInTeam,
    }.get(first.code, errors.ValidationError)
    raise cls(first.message, details=[ErrorDetail(field=str(v.player_ids) if v.player_ids else None, reason=v.message) for v in vr.violations])


def run(db: Session, event: Event, by: User, body: AssignmentRunRequest) -> tuple[AssignmentRun, list[str]]:
    """배정 실행: 검증 → 완전 탐색 → 전략별 후보안 저장. 반환: (저장된 실행, 경고 문구).

    실행 기록을 쌓아 두지 않는다. 확정하지 않고 흘려보낸 지난 실행은 여기서 지우고, 확정한 편성만
    `adopt()` 때까지 남긴다 — 그래야 새 안을 짜 보는 동안에도 플레이어에게 직전 배정이 계속 보인다.
    돌려주는 실행은 후보안·팀·슬롯·제약까지 다 읽어 둔 상태라, 응답을 만들 때 관계를 하나씩 다시 읽지 않는다.
    """
    if event.status == EventStatus.CANCELED:
        raise errors.ValidationError("취소된 일정은 배정할 수 없어요.")
    _lock_event(db, event.id)  # 같은 일정의 실행 · 확정이 겹치지 않게 (지난 실행 정리와 확정이 서로를 지우지 않게)
    ensure_unlocked(db, event.id)
    roster = build_roster(db, event)
    prep = prepare(roster, body)
    vr = _validate_prepared(prep)
    if not vr.feasible:
        _raise_violations(vr)
    ids = [r.id for r in roster]
    pref_pairs = _load_pref_pairs(db, ids)
    recent = _load_recent_pairs(db, event)
    if body.team_count == 2 and len(prep.supernodes) <= MAX_SUPERNODES:
        scored = score_partitions(prep, list(enumerate_partitions(prep)), pref_pairs, recent)
        search, evaluated = "exhaustive", len(scored)
    else:  # 3팀, 또는 18명(묶음 뒤)이 넘는 2팀 — 완전 탐색은 너무 오래 걸린다
        scored, evaluated = search_partitions(prep, pref_pairs, recent, body.strategies)
        search = "local_search"
        _warn_uneven(prep, _squad_sizes(len(roster), body.team_count))
    if any(s.hard_ok for s in scored):
        pool = [s for s in scored if s.hard_ok]
    else:
        pool = scored
        prep.warnings.append(f"{'양 팀' if body.team_count == 2 else '모든 팀'}에 볼 운반·골밑 자원을 다 넣을 수 없어 이 조건은 접었어요")

    _drop_unadopted_runs(db, event)  # 검증을 통과한 뒤에 정리한다 — 실패한 실행 때문에 지난 안을 잃지 않도록
    run_row = AssignmentRun(
        event_id=event.id, executed_by=by.id, team_count=body.team_count,
        params={"strategies": [s.value for s in body.strategies], "weights": {k.value: v for k, v in STRATEGY_WEIGHTS.items()}, "w_fair": W_FAIR, "w_guest": W_GUEST, "search": search, "partitions_evaluated": evaluated},
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
    players = {r.id: r.player for r in roster}
    loaded = db.get(
        AssignmentRun, run_row.id,
        options=[
            selectinload(AssignmentRun.constraints),
            selectinload(AssignmentRun.candidates).selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots),
        ],
        populate_existing=True,
    )
    loaded._roster_players = players  # type: ignore[attr-defined]  # run_view 가 선수를 다시 읽지 않도록 (명단은 방금 읽었다)
    return loaded, prep.warnings


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
    """후보안 하나를 팀·슬롯까지 객체 그래프로 만들어 flush 한 번에 저장한다 (팀마다 따로 INSERT 하지 않는다)."""
    positions: dict[int, Position | None] = {}
    squads = []
    for i, s in enumerate(sc.squads):
        pos = assign_positions(s)
        positions.update(pos)
        squads.append(AssignmentSquad(
            squad_no=i + 1, squad_name=SQUAD_NAMES[i], avg_skill=Decimal(str(round(sc.terms["means"][i], 1))),
            slots=[AssignmentSlot(player_id=r.id, assigned_position=pos.get(r.id)) for r in s],
        ))
    cand = AssignmentCandidate(
        run_id=run_row.id, strategy=strategy, total_score=Decimal(str(round(sc.total(STRATEGY_WEIGHTS[strategy]), 3))),
        metrics={
            **metrics_of(sc), "player_explanation": explain_player(sc, positions),
            # 수동 수정 초기화용 원본 편성 (squad_no → player_ids)
            "original_squads": {str(i + 1): [r.id for r in s] for i, s in enumerate(sc.squads)},
        },
        explanation=explain_manager(sc, strategy, prep), squads=squads,
    )
    db.add(cand)  # flush 는 run() 이 후보안을 다 만든 뒤 한 번에 (commit)
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


def players_of(db: Session, ids: list[int]) -> dict[int, Player]:
    return {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(ids)).options(*PLAYER_LOAD)).all()}


def _avg_height(players: list[Player]) -> float | None:
    hs = [h for h in ((p.height_cm if p.user is None else p.user.height_cm) for p in players) if h]  # 게스트 키(players.height_cm) 포함
    return round(mean(hs), 1) if hs else None


def squad_views(db: Session, cand: AssignmentCandidate, *, mask: bool, players: dict[int, Player] | None = None) -> list[SquadView]:
    """`players` 를 주면 참가자 조회를 건너뛴다 — 한 실행의 후보안 3개는 같은 사람들이라 한 번만 읽으면 된다."""
    ids = [s.player_id for sq in cand.squads for s in sq.slots]
    if players is None:
        players = players_of(db, ids)
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


def candidate_view(db: Session, cand: AssignmentCandidate, *, mask: bool = False, players: dict[int, Player] | None = None) -> CandidateView:
    return CandidateView(
        id=cand.id, strategy=cand.strategy, total_score=cand.total_score, metrics=cand.metrics,
        explanation=cand.metrics.get("player_explanation") if mask else cand.explanation,
        is_adopted=cand.is_adopted, squads=squad_views(db, cand, mask=mask, players=players),
    )


def run_view(db: Session, run_row: AssignmentRun, warnings: list[str] | None = None) -> AssignmentRunView:
    ids = list({s.player_id for c in run_row.candidates for sq in c.squads for s in sq.slots})
    players = getattr(run_row, "_roster_players", None) or (players_of(db, ids) if ids else {})
    return AssignmentRunView(
        id=run_row.id, event_id=run_row.event_id, team_count=run_row.team_count, created_at=run_row.created_at,
        constraints=constraints_of(run_row), candidates=[candidate_view(db, c, players=players) for c in run_row.candidates],
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
        .limit(1)  # 없으면 지난 run 전부와 그 제약까지 읽어 온다
    )
    if prev is None:
        raise errors.NotFound("지난 일정의 팀 배정 기록이 없어요.")
    return constraints_of(prev)


def get_run(db: Session, run_id: int) -> AssignmentRun:
    return _load_run(db, run_id)


def load_candidate(db: Session, candidate_id: int) -> AssignmentCandidate:
    # populate_existing: 슬롯의 squad_id 를 바꾼 뒤에도 식별 맵의 stale 컬렉션이 아니라 DB 상태를 다시 읽는다
    c = db.get(
        AssignmentCandidate, candidate_id,
        options=[selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots), selectinload(AssignmentCandidate.run).selectinload(AssignmentRun.constraints)],
        populate_existing=True,
    )
    if c is None:
        raise errors.NotFound("배정안을 찾을 수 없어요.")
    return c


def _separate_group_of(cand: AssignmentCandidate) -> dict[int, int]:
    """player_id → 갈라놓기 group_no. 갈라놓은 사람은 한 명만 옮길 수 없고 같은 그룹끼리 맞교체만 된다."""
    return {c.player_id: c.group_no for c in cand.run.constraints if c.type == ConstraintType.SEPARATE}


def _lock_groups_of(cand: AssignmentCandidate) -> dict[int, set[int]]:
    groups: dict[int, set[int]] = defaultdict(set)
    for c in cand.run.constraints:
        if c.type == ConstraintType.LOCK:
            groups[c.group_no].add(c.player_id)
    return {pid: members for members in groups.values() for pid in members}


def edit(
    db: Session, cand: AssignmentCandidate, *, swaps: list[SwapPair] = (), moves: list[MovePlayer] = (), exchanges: list[Exchange] = (),
) -> AssignmentCandidate:
    """`PATCH /assignments/candidates/{id}` 한 번의 수정 — 맞교체 → 옮기기 → 그룹 교환 순으로 적용하고 **한 번만** 저장한다.

    어느 단계에서든 검증에 걸리면 아무것도 저장하지 않는다 (예전에는 swaps 를 저장한 뒤 moves 에서 422 가 나면 반만 바뀌었다).
    """
    if cand.is_adopted:
        raise errors.AlreadyAdopted("확정된 후보안은 수정할 수 없어요. 재배정을 실행해 주세요.")
    ensure_unlocked(db, cand.run.event_id)
    if swaps:
        _apply_exchanges(cand, [Exchange(a_player_ids=[sw.player_id_a], b_player_ids=[sw.player_id_b]) for sw in swaps])
    if moves:
        _apply_exchanges(cand, _moves_to_exchanges(cand, moves))  # 앞 단계에서 바뀐 소속을 기준으로 검사한다
    if exchanges:
        _apply_exchanges(cand, list(exchanges))
    _reload_slots(db, cand)
    _recompute_candidate(db, cand)
    db.commit()
    return load_candidate(db, cand.id)


def exchange(db: Session, cand: AssignmentCandidate, exchanges: list[Exchange]) -> AssignmentCandidate:
    """그룹 단위 교환만 하는 수정 (`edit` 의 한 경우)."""
    return edit(db, cand, exchanges=exchanges)


def _apply_exchanges(cand: AssignmentCandidate, exchanges: list[Exchange]) -> None:
    """그룹 단위 교환: a 쪽은 상대 팀으로, b 쪽은 a 팀으로. 한쪽이 비면 일방 이동. 메모리의 슬롯만 바꾼다 (flush 안 함).

    - 묶음(LOCK)에 속한 사람이 있으면 묶음 전체를 자동으로 포함한다 (묶음은 통째로만 움직인다).
    - 갈라놓기(SEPARATE)는 교환 뒤에도 서로 다른 팀이어야 한다 (짝을 반대편에 함께 넣으면 통과).
    - 사전 배치(PIN)는 옮길 수 없다. 각 팀에 최소 5명은 남아야 한다.
    """
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
        id_of_no = {sq.squad_no: sq.id for sq in cand.squads}
        target = id_of_no.get(ex.to_squad_no) if ex.to_squad_no is not None else None
        if ex.to_squad_no is not None and target is None:
            raise errors.InvalidSwap("없는 팀이에요.")
        if sq_a and sq_b:  # 맞교체: a 는 b 의 팀으로, b 는 a 의 팀으로
            src_a, src_b = next(iter(sq_a)), next(iter(sq_b))
        elif len(squad_ids) == 2:  # 일방 이동 — 2팀이면 상대 팀이 정해져 있다
            src_a = next(iter(sq_a)) if sq_a else next(i for i in squad_ids if i not in sq_b)
            src_b = next(iter(sq_b)) if sq_b else next(i for i in squad_ids if i != src_a)
        else:  # 3팀 일방 이동은 옮길 팀(to_squad_no)이 있어야 한다
            if target is None:
                raise errors.InvalidSwap("옮길 팀을 골라 주세요.")
            src = next(iter(sq_a or sq_b))
            if target == src:
                raise errors.InvalidSwap("이미 그 팀에 있어요.")
            src_a, src_b = (src, target) if sq_a else (target, src)
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
            if sum(1 for v in new_sq.values() if v == sid) < MIN_SQUAD:
                raise errors.InvalidSwap(f"{name_of[sid]} 팀에 최소 {MIN_SQUAD}명은 남아야 해요.")
        for pid in a | b:
            slot_of[pid].squad_id = new_sq[pid]
            slot_of[pid].is_manual_override = True


def swap(db: Session, cand: AssignmentCandidate, swaps: list[SwapPair]) -> AssignmentCandidate:
    """두 선수 맞교체 — Exchange 1:1 로 위임 (묶음은 자동 확장)."""
    return edit(db, cand, swaps=swaps)


def move(db: Session, cand: AssignmentCandidate, moves: list[MovePlayer]) -> AssignmentCandidate:
    """한 명(또는 묶음)을 지정한 팀으로 일방 이동 — Exchange 한쪽 비움으로 위임."""
    return edit(db, cand, moves=moves)


def _moves_to_exchanges(cand: AssignmentCandidate, moves: list[MovePlayer]) -> list[Exchange]:
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
        exs.append(Exchange(a_player_ids=[mv.player_id], b_player_ids=[], to_squad_no=mv.to_squad_no))
    return exs


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
    ensure_unlocked(db, cand.run.event_id)
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
    return load_candidate(db, cand.id)


def _recompute_candidate(db: Session, cand: AssignmentCandidate, *, manual: bool = True) -> None:
    """고친 편성을 다시 채점한다. 명단은 지금의 참석 응답이 아니라 이 후보안에 든 사람들이다 — 배정 뒤 참석을 바꾼
    사람이 1팀 점수에 섞이거나 빠지지 않게 (재배정은 따로 한다)."""
    event = db.get(Event, cand.run.event_id)
    ids = [s.player_id for sq in cand.squads for s in sq.slots]
    roster = _roster_from(sorted(players_of(db, ids).values(), key=lambda p: p.display_name))
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

    동시성: 일정 행을 `SELECT … FOR UPDATE` 로 잠근 뒤 후보안을 다시 읽는다. 같은 실행의 두 안을 동시에 확정하면 뒤에 온
    쪽은 앞 쪽이 끝난 뒤의 상태를 보고 409 ALREADY_ADOPTED, 다른 실행의 안을 동시에 확정해도 서로를 지우다 교착되지 않는다
    (앞 쪽이 지운 실행의 안이면 409).
    """
    event_id = cand.run.event_id
    _lock_event(db, event_id)
    ensure_unlocked(db, event_id)
    fresh = db.get(
        AssignmentCandidate, cand.id,
        options=[selectinload(AssignmentCandidate.run).selectinload(AssignmentRun.candidates)], populate_existing=True,
    )
    if fresh is None:  # 다른 실행의 안이 먼저 확정되면서 이 실행이 지워졌다
        raise errors.AlreadyAdopted("다른 배정안이 먼저 확정됐어요. 화면을 새로고침해 주세요.")
    cand = fresh
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
    return load_candidate(db, cand.id)


def _lock_event(db: Session, event_id: int) -> None:
    """일정 행을 트랜잭션 끝까지 잠근다 (SELECT … FOR UPDATE). 배정 실행 · 확정이 같은 일정에서 겹치지 않게."""
    db.execute(select(Event.id).where(Event.id == event_id).with_for_update())


def ensure_unlocked(db: Session, event_id: int) -> None:
    """쿼터 기록이 있는 일정은 팀을 다시 짜거나 확정을 바꿀 수 없다 — 기록(누가 어느 팀으로 뛰었나)이 그 편성을 근거로 한다."""
    if db.scalar(select(Quarter.id).where(Quarter.event_id == event_id).limit(1)) is not None:
        raise errors.AssignmentLocked()


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
        .options(selectinload(AssignmentCandidate.squads).selectinload(AssignmentSquad.slots), contains_eager(AssignmentCandidate.run))
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
