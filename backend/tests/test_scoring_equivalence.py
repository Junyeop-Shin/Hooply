"""완전 탐색 채점: 행렬 구현(score_partitions)이 기준 구현(score_partition)과 같은 값을 내는지.

DB 없이 돌아간다 — Player 객체를 세션에 넣지 않고 만들어 명단을 꾸민다. 묶기·갈라놓기·사전 배치가
섞인 조건과 선호 조합·최근 같은 팀 쌍을 무작위로 넣어, 모든 분할에서 항 하나하나가 일치해야 한다.
"""

import random

import pytest

from app.models import Player
from app.models.enums import PlayerKind, Position
from app.schemas.assignment import AssignmentRunRequest, ConstraintSet, PinConstraint
from app.services import assignment_service as a

POS = list(Position)


def _roster(n: int, seed: int) -> list[a.RosterPlayer]:
    rng = random.Random(seed)
    out = []
    for i in range(1, n + 1):
        playable = set(rng.sample(POS, rng.randint(1, 3)))
        primary = rng.choice(sorted(playable, key=POS.index)) if rng.random() < 0.9 else None
        p = Player(id=i, team_id=1, kind=PlayerKind.GUEST if i % 6 == 0 else PlayerKind.MEMBER, display_name=f"p{i}")
        out.append(a.RosterPlayer(player=p, skill=rng.uniform(-3, 3), known=i % 6 != 0, playable=playable, primary=primary, pref_rank={primary: 1} if primary else {}))
    return out


@pytest.mark.parametrize("n,seed", [(12, 1), (13, 2), (15, 3), (16, 4)])
def test_batch_scoring_matches_reference(n, seed):
    rng = random.Random(seed)
    roster = _roster(n, seed)
    ids = [r.id for r in roster]
    body = AssignmentRunRequest(team_count=2, constraints=ConstraintSet(
        lock_groups=[[ids[0], ids[1], ids[2]]], separate_groups=[[ids[3], ids[4]]], pins=[PinConstraint(player_id=ids[5], squad_no=1)],
    ))
    prep = a.prepare(roster, body)
    assert not prep.violations
    pref = {(x, y): round(rng.uniform(0.1, 1.5), 2) for x, y in [tuple(sorted(rng.sample(ids, 2))) for _ in range(n)]}
    recent = {tuple(sorted(rng.sample(ids, 2))) for _ in range(n * 2)}

    parts = list(a.enumerate_partitions(prep))
    assert parts
    batch = a.score_partitions(prep, parts, pref, recent)
    for part, sc in zip(parts, batch, strict=True):
        ref = a.score_partition(prep, part, pref, recent)
        assert sc.partition == part
        assert sc.hard_ok == ref.hard_ok
        for key in ("skill", "position", "pref", "role", "fair", "guest"):
            assert sc.terms[key] == pytest.approx(ref.terms[key], abs=1e-9), (key, part)
        assert sc.terms["means"] == pytest.approx(ref.terms["means"], abs=1e-9)
        # 팀 명단은 필요할 때 만들어지지만 내용은 같아야 한다
        assert [[r.id for r in s] for s in sc.squads] == [[r.id for r in s] for s in ref.squads]


def test_batch_scoring_without_pairs_skips_pair_terms():
    roster = _roster(12, 9)
    prep = a.prepare(roster, AssignmentRunRequest(team_count=2))
    parts = list(a.enumerate_partitions(prep))
    for sc in a.score_partitions(prep, parts, {}, set()):
        assert sc.terms["pref"] == 0.0 and sc.terms["fair"] == 0.0
