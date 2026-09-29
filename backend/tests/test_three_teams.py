"""3팀 배정 (설계서 13.1절 Q4 — 참석 16명 이상이면 7·7·7 같은 세 팀). DB 없이 배정 엔진만 본다.

- 행렬 채점이 3팀에서도 기준 구현과 같은 값을 낸다
- 지역 탐색이 15명(5·5·5, 편성 12만 6천 개)에서 완전 탐색의 최적과 같은 값을 찾는다
- 묶기 · 갈라놓기 · 사전 배치를 늘 지키고, 후보안 편성이 서로 다르다
"""

import itertools
import random
import time

import numpy as np
import pytest

from app.models.enums import Strategy
from app.schemas.assignment import AssignmentRunRequest, ConstraintSet, PinConstraint
from app.services import assignment_service as a
from tests.test_ranking_assignment import _event_with_attendance, club  # noqa: F401
from tests.test_scoring_equivalence import _roster

ALL = [Strategy.SKILL, Strategy.CHEMISTRY, Strategy.BALANCED]


def _pairs(ids, n, seed):
    rng = random.Random(seed)
    pref = {tuple(sorted(rng.sample(ids, 2))): round(rng.uniform(0.1, 1.5), 2) for _ in range(n)}
    recent = {tuple(sorted(rng.sample(ids, 2))) for _ in range(n * 2)}
    return pref, recent


def _squads_ok(prep, part):
    sizes = [sum(len(prep.supernodes[i]) for i, s in enumerate(part) if s == sq) for sq in range(prep.team_count)]
    assert min(sizes) >= 5
    for x, y in prep.separate_pairs:
        assert part[x] != part[y]
    for node, sq in prep.pins.items():
        assert part[node] == sq
    return sizes


def test_three_team_batch_scoring_matches_reference():
    roster = _roster(21, 5)
    ids = [r.id for r in roster]
    prep = a.prepare(roster, AssignmentRunRequest(team_count=3, constraints=ConstraintSet(lock_groups=[ids[:3]])))
    assert not prep.violations
    pref, recent = _pairs(ids, 21, 5)
    rng = random.Random(1)
    parts = [tuple(rng.randrange(3) for _ in prep.supernodes) for _ in range(40)]
    for part, sc in zip(parts, a.score_partitions(prep, parts, pref, recent), strict=True):
        ref = a.score_partition(prep, part, pref, recent)
        assert sc.hard_ok == ref.hard_ok
        for key in ("skill", "position", "pref", "role", "fair", "guest"):
            assert sc.terms[key] == pytest.approx(ref.terms[key], abs=1e-9), key
        assert sc.terms["means"] == pytest.approx(ref.terms["means"], abs=1e-9)


def _all_555(n_nodes):
    """15개 노드를 5·5·5 로 나누는 모든 방법 (팀 이름만 바뀐 중복 제거) — 12만 6천 개."""
    nodes = list(range(n_nodes))
    for t0 in itertools.combinations(nodes[1:], 4):
        team0 = {0, *t0}
        rest = [x for x in nodes if x not in team0]
        for t1 in itertools.combinations(rest[1:], 4):
            team1 = {rest[0], *t1}
            yield tuple(0 if x in team0 else 1 if x in team1 else 2 for x in nodes)


@pytest.mark.parametrize("seed", [11, 12])
def test_local_search_finds_exhaustive_optimum_on_15(seed):
    roster = _roster(15, seed)
    ids = [r.id for r in roster]
    prep = a.prepare(roster, AssignmentRunRequest(team_count=3))
    pref, recent = _pairs(ids, 15, seed)
    parts = list(_all_555(len(prep.supernodes)))
    st = a._node_stats(prep, pref, recent)
    prep.skill_sd = a._skill_sd(prep)
    tm = a._terms_matrix(prep, st, np.asarray(parts, dtype=int), len(recent))
    found, _ = a.search_partitions(prep, pref, recent, ALL)
    for strategy in ALL:
        w = a.STRATEGY_WEIGHTS[strategy]
        best = float(a._totals(tm, w).min())
        got = min(sc.total(w) for sc in found)
        assert got == pytest.approx(best, abs=1e-9), strategy


def test_three_teams_21_players_7_7_7_with_constraints_and_distinct_candidates():
    roster = _roster(21, 7)
    ids = [r.id for r in roster]
    body = AssignmentRunRequest(team_count=3, constraints=ConstraintSet(
        lock_groups=[[ids[0], ids[1]], [ids[2], ids[3], ids[4]]], separate_groups=[[ids[5], ids[6]], [ids[7], ids[8]]],
        pins=[PinConstraint(player_id=ids[9], squad_no=3), PinConstraint(player_id=ids[10], squad_no=1)],
    ))
    prep = a.prepare(roster, body)
    assert not prep.violations
    pref, recent = _pairs(ids, 21, 7)
    t0 = time.perf_counter()
    found, evaluated = a.search_partitions(prep, pref, recent, ALL)
    assert time.perf_counter() - t0 < 5  # 실제 서버에서 기다릴 만한 시간
    assert len(found) >= 3 and evaluated > len(found)
    for sc in found:
        assert sorted(_squads_ok(prep, sc.partition)) == [7, 7, 7]
        squads = [{r.id for r in s} for s in sc.squads]
        assert any({ids[0], ids[1]} <= s for s in squads) and any({ids[2], ids[3], ids[4]} <= s for s in squads)
        assert ids[9] in squads[2] and ids[10] in squads[0]
    # 같은 입력이면 같은 결과 (고정 시드)
    again, _ = a.search_partitions(a.prepare(roster, body), pref, recent, ALL)
    assert sorted(s.partition for s in again) == sorted(s.partition for s in found)


def test_three_teams_need_15_and_uneven_sizes():
    prep = a.prepare(_roster(14, 3), AssignmentRunRequest(team_count=3))
    assert any(v.code == "NOT_ENOUGH_PLAYERS" and "최소 15명" in v.message for v in prep.violations)
    prep = a.prepare(_roster(20, 3), AssignmentRunRequest(team_count=3))
    assert not prep.violations
    found, _ = a.search_partitions(prep, {}, set(), [Strategy.SKILL])
    assert sorted(_squads_ok(prep, found[0].partition)) == [6, 7, 7]
    assert a.prepare(_roster(21, 3), AssignmentRunRequest.model_construct(team_count=4, strategies=ALL, constraints=ConstraintSet())).violations


def test_three_teams_infeasible_separate_is_reported():
    roster = _roster(16, 4)
    ids = [r.id for r in roster]
    # 네 사람을 모두 서로 갈라놓으면 3팀으로는 불가능
    seps = [list(p) for p in itertools.combinations(ids[:4], 2)]
    prep = a.prepare(roster, AssignmentRunRequest(team_count=3, constraints=ConstraintSet(separate_groups=seps)))
    vr = a._validate_prepared(prep)
    assert not vr.feasible and vr.violations[0].code == "SEPARATE_INFEASIBLE"


# ---------------------------------------------------------------------------
# API — 21명(회원 12 + 게스트 9)을 3팀으로: 실행 → 옮기기 · 맞교체 → 확정 → 쿼터 대진 → 팀별 요약
# ---------------------------------------------------------------------------


API = "/api/v1"


def test_three_team_flow_api(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club, guests=9)
    v = client.post(f"{API}/events/{eid}/assignments:validate", json={"team_count": 3}, headers=m).json()
    assert v["feasible"] is True, v
    r = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 3}, headers=m)
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["team_count"] == 3
    parts = []
    for c in run["candidates"]:
        assert [s["squad_name"] for s in c["squads"]] == ["블랙", "화이트", "레드"]
        assert sorted(len(s["members"]) for s in c["squads"]) == [7, 7, 7]
        assert c["metrics"]["team_count"] == 3 and "세 팀" in c["explanation"] + c["metrics"]["player_explanation"]
        parts.append(tuple(sorted(tuple(sorted(mb["id"] for mb in s["members"])) for s in c["squads"])))
    assert len(set(parts)) == 3  # 후보안 세 개의 편성이 서로 다르다

    cand = run["candidates"][0]
    sq = {s["squad_no"]: [mb["id"] for mb in s["members"]] for s in cand["squads"]}
    # 3팀 일방 이동은 옮길 팀이 있어야 한다
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"exchanges": [{"a_player_ids": [sq[1][0]], "b_player_ids": []}]}, headers=m)
    assert r.status_code == 422 and "옮길 팀" in r.json()["message"]
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"moves": [{"player_id": sq[1][0], "to_squad_no": 3}]}, headers=m)
    assert r.status_code == 200, r.text
    after = {s["squad_no"]: [mb["id"] for mb in s["members"]] for s in r.json()["squads"]}
    assert sq[1][0] in after[3] and len(after[1]) == 6 and len(after[3]) == 8
    # 블랙 ↔ 레드 맞교체
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"exchanges": [{"a_player_ids": [after[3][0]], "b_player_ids": [after[1][0]]}]}, headers=m)
    assert r.status_code == 200, r.text
    assert client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m).status_code == 200

    adopted = client.get(f"{API}/events/{eid}/assignment/adopted", headers=m).json()
    squads = {s["squad_no"]: [mb["id"] for mb in s["members"]] for s in adopted["squads"]}
    assert len(squads) == 3

    def q(no, home, away, hs, as_):
        return {"quarter_no": no, "black_score": hs, "white_score": as_, "home_squad_no": home, "away_squad_no": away, "duration_min": 8,
                "lineups": [{"player_id": p, "side": "BLACK"} for p in squads[home][:5]] + [{"player_id": p, "side": "WHITE"} for p in squads[away][:5]]}

    bad = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [q(1, 2, 2, 5, 3)]}, headers=m)
    assert bad.status_code in (400, 422)
    r = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [q(1, 1, 2, 10, 8), q(2, 2, 3, 6, 9), q(3, 3, 1, 7, 7)]}, headers=m)
    assert r.status_code == 200, r.text
    body = client.get(f"{API}/events/{eid}/quarters", headers=m).json()
    assert [(x["home_squad_no"], x["away_squad_no"]) for x in body["items"]] == [(1, 2), (2, 3), (3, 1)]
    s = body["summary"]
    assert s["team_count"] == 3
    t = {x["squad_no"]: x for x in s["squads"]}
    assert (t[1]["quarters"], t[1]["points_for"], t[1]["points_against"], t[1]["wins"], t[1]["losses"]) == (2, 17, 15, 1, 0)
    assert (t[2]["wins"], t[2]["losses"], t[3]["wins"], t[3]["losses"]) == (0, 2, 1, 0)
    assert t[3]["squad_name"] == "레드"
    # 레드 선수는 레드로 묶인다 (칸이 아니라 팀)
    red = next(p for p in s["per_player"] if p["player_id"] == squads[3][0])
    assert red["squad_no"] == 3

    # 전술 추천도 세 팀 모두
    rec = client.get(f"{API}/events/{eid}/tactics/recommend", headers=m).json()
    assert [x["squad_no"] for x in rec["squads"]] == [1, 2, 3]
