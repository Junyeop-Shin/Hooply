"""매니저 실력 정렬(F14) · 팀 배정(F5 · F6 · F7 · F15) 흐름.

시나리오: 매니저 + 팀원 11 = 12명 팀. 설문·자기 위치로 실력이 갈리고, 포지션이 골고루 있는 상태에서
일정을 열어 12명 + 게스트 2명이 참석한다. 묶기 제약을 걸어 배정을 돌리고, 후보안 3개·교체·확정·플레이어 뷰를 확인한다.
13.4절 검증 방법: "제약이 걸린 모든 경우에 묶인 사람이 같은 팀인가" 를 무작위 묶음으로 반복 확인한다.
"""

import random

import pytest

from tests.test_survey_guest_event import _submit, _template

API = "/api/v1"

# 12명 구성: (이름, 자기 위치, 선호 포지션 순서, D3A 1번, D3B 5번)
ROSTER = [
    ("최준용", "TOP10", ("PG", "SG"), "CAN_PREFER", "CANNOT"),
    ("이정현", "TOP10", ("C", "PF"), "CANNOT", "CAN_PREFER"),
    ("함지훈", "TOP30", ("SF", "PF"), "CANNOT", "CAN_NO_PREFER"),
    ("이규섭", "TOP30", ("SG", "SF"), "CAN_NO_PREFER", "CANNOT"),
    ("양희승", "MID", ("PF", "C"), "CANNOT", "CAN_PREFER"),
    ("변기훈", "MID", ("PG",), "CAN_PREFER", "CANNOT"),
    ("정영삼", "MID", ("SF", "SG"), "CANNOT", "CANNOT"),
    ("김진", "BOT30", ("SG", "PG"), "CAN_NO_PREFER", "CANNOT"),
    ("신동파", "BOT30", ("SF",), "CANNOT", "CANNOT"),
    ("라건아", "BOT30", ("C",), "CANNOT", "CAN_PREFER"),
    ("김단비", "BOT10", ("PF", "SF"), "CANNOT", "CAN_NO_PREFER"),
    ("박지수", "BOT10", ("SG",), "CANNOT", "CANNOT"),
]


@pytest.fixture
def club(client, signup):
    """12명 팀(ACTIVE) + 설문·자기 위치 완료. 반환: manager 헤더, members 헤더 목록, team_id, name→player_id."""
    tpl = _template(client)
    manager = signup("mgr@club.com", name=ROSTER[0][0])
    team = client.post(f"{API}/teams", json={"name": "일요농구"}, headers=manager).json()
    tid, code = team["id"], team["team_code"]
    headers = [manager]
    for email_i, (name, lvl, d1, pg, c) in enumerate(ROSTER):
        h = manager if email_i == 0 else signup(f"p{email_i}@club.com", name=name)
        if email_i:
            assert client.post(f"{API}/teams/join", json={"team_code": code}, headers=h).status_code == 200
            headers.append(h)
        client.patch(f"{API}/me", json={"height_cm": 170 + email_i * 2}, headers=h)  # 평균 신장 계산용
        _submit(client, h, tpl, a3="AMATEUR" if lvl.startswith("TOP") else ("CLUB" if lvl == "MID" else "STREET"), d1=d1, pg=pg, c=c)
        assert client.put(f"{API}/teams/{tid}/self-rank", json={"level": lvl}, headers=h).status_code == 200
    cards = client.get(f"{API}/teams/{tid}/players", headers=manager).json()["items"]
    return {"manager": manager, "members": headers, "team_id": tid, "pid": {c["display_name"]: c["id"] for c in cards}}


def _event_with_attendance(client, club, guests=2):
    m, tid = club["manager"], club["team_id"]
    eid = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-09-13", "title": "일요 정기전"}, headers=m).json()["id"]
    for h in club["members"]:
        assert client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h).status_code == 200
    guest_ids = []
    for i in range(guests):
        r = client.post(f"{API}/events/{eid}/guests", json={"display_name": f"게스트{i}", "skill_grade": 3 if i == 0 else None, "playable_positions": ["SF"], "preferred_position": "SF", "team_lock_request": i == 0}, headers=club["members"][1])
        assert r.status_code == 201, r.text
        guest_ids.append(r.json()["player"]["id"])
    return eid, guest_ids


# ---------------------------------------------------------------------------
# F14 매니저 정렬
# ---------------------------------------------------------------------------


# 검증: FR-14 · 8.5절 — 정렬 저장 → 새 버전 활성, 이전 버전 비활성, 순위가 prior 에 반영(설문 0.5 + 정렬 0.5)
def test_manager_ranking_versions_and_prior(client, club):
    m, tid, pid = club["manager"], club["team_id"], club["pid"]
    assert client.get(f"{API}/teams/{tid}/rankings/latest", headers=m).json()["code"] == "NO_RANKING"
    assert client.post(f"{API}/teams/{tid}/rankings", json={"player_ids": [pid["최준용"], pid["이정현"]]}, headers=club["members"][1]).status_code == 403

    before = {c["display_name"]: float(c["prior_overall"]) for c in client.get(f"{API}/teams/{tid}/players", headers=m).json()["items"]}
    # 설문상 하위(박지수)를 1위로 올린 정렬
    order = ["박지수"] + [n for n, *_ in ROSTER if n != "박지수"]
    r = client.post(f"{API}/teams/{tid}/rankings", json={"player_ids": [pid[n] for n in order]}, headers=m)
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert v1["is_active"] and [e["player"]["display_name"] for e in v1["entries"]][:2] == ["박지수", "최준용"]
    after = {c["display_name"]: float(c["prior_overall"]) for c in client.get(f"{API}/teams/{tid}/players", headers=m).json()["items"]}
    assert after["박지수"] > before["박지수"]  # 정렬 1위 → 상승
    assert after["박지수"] > after["김단비"]  # 설문상 둘 다 하위 10% 였지만 정렬(1위 vs 12위)이 갈라놓는다

    # 두 번째 버전 → 첫 버전 비활성, 이력 2개
    r = client.post(f"{API}/teams/{tid}/rankings", json={"player_ids": [pid[n] for n, *_ in ROSTER]}, headers=m)
    assert r.status_code == 201
    hist = client.get(f"{API}/teams/{tid}/rankings", headers=m).json()["items"]
    assert len(hist) == 2 and hist[0]["is_active"] and not hist[1]["is_active"]
    assert client.get(f"{API}/teams/{tid}/rankings/latest", headers=m).json()["id"] == hist[0]["id"]
    # 다른 팀 참가자 → 422
    r = client.post(f"{API}/teams/{tid}/rankings", json={"player_ids": [pid["최준용"], 999999]}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAYER_NOT_IN_TEAM"


# ---------------------------------------------------------------------------
# F5 · F15 배정
# ---------------------------------------------------------------------------


# 검증: FR-16 · FR-17 · FR-21 · FR-34 — 후보안 3개가 서로 다르고, 묶음이 모든 전략에서 같은 팀이며,
#       각 팀에 1번·5번 가능자가 있고, 팀 크기가 7/7 이고, 게스트가 한쪽에 몰리지 않는다
def test_assignment_run_candidates(client, club):
    m = club["manager"]
    eid, guests = _event_with_attendance(client, club)
    # 묶기 제안(게스트0 ↔ 등록자 팀원1) 확인 후 승인 → lock_groups
    sug = client.get(f"{API}/events/{eid}/assignment/suggestions", headers=m).json()["items"]
    assert len(sug) == 1 and sug[0]["guest"]["id"] == guests[0]
    lock = [sug[0]["guest"]["id"], sug[0]["target"]["id"]]
    pair = [club["pid"]["함지훈"], club["pid"]["이규섭"]]  # 등록자(이정현)와 겹치지 않는 두 번째 묶음
    body = {"team_count": 2, "strategies": ["SKILL", "CHEMISTRY", "BALANCED"], "constraints": {"lock_groups": [lock, pair]}}

    v = client.post(f"{API}/events/{eid}/assignments:validate", json=body, headers=m).json()
    assert v["feasible"] and any("게스트 1명" in w for w in v["warnings"])

    r = client.post(f"{API}/events/{eid}/assignments", json=body, headers=m)
    assert r.status_code == 201, r.text
    run = r.json()
    assert [c["strategy"] for c in run["candidates"]] == ["SKILL", "CHEMISTRY", "BALANCED"]
    assert len(run["constraints"]["lock_groups"]) == 2
    partitions = set()
    for cand in run["candidates"]:
        squads = cand["squads"]
        assert [s["squad_name"] for s in squads] == ["블랙", "화이트"]
        sizes = sorted(len(s["members"]) for s in squads)
        assert sizes == [7, 7]
        for s in squads:
            ids = {mbr["id"] for mbr in s["members"]}
            # 묶음은 통째로
            for g in (lock, pair):
                assert len(ids & set(g)) in (0, len(g))
            playable = [set(mbr["playable_positions"]) for mbr in s["members"]]
            assert any("PG" in p for p in playable) and any(p & {"PF", "C"} for p in playable)
            assert all(str(pid) in s["assigned_positions"] for pid in ids)  # JSON 키는 문자열
        assert cand["metrics"]["hard_constraints_met"] is True
        assert max(cand["metrics"]["guest_count_per_squad"]) - min(cand["metrics"]["guest_count_per_squad"]) <= 1
        assert cand["explanation"] and "평균" in cand["explanation"]
        assert cand["metrics"]["player_explanation"]
        partitions.add(frozenset(frozenset(mbr["id"] for mbr in s["members"]) for s in squads))
    assert len(partitions) == 3  # 후보안끼리 편성이 다르다
    # 실력 우선안은 평균 차이가 가장 작거나 같아야 한다
    spread = {c["strategy"]: c["metrics"]["skill_spread"] for c in run["candidates"]}
    assert spread["SKILL"] <= spread["CHEMISTRY"] + 1e-9

    # 이력·조회·플레이어 권한
    assert len(client.get(f"{API}/events/{eid}/assignments", headers=m).json()["items"]) == 1
    assert client.get(f"{API}/assignments/runs/{run['id']}", headers=m).status_code == 200
    assert client.get(f"{API}/assignments/runs/{run['id']}", headers=club["members"][1]).status_code == 403
    assert client.get(f"{API}/events/{eid}/assignment/adopted", headers=club["members"][1]).json()["code"] == "NOT_ADOPTED_YET"


# 검증: 9.6절 사전 검사 표 — 인원 부족·그룹 과대·묶기/갈라놓기 충돌·PIN 정원 초과·비참석자 포함이 실행 전에 차단된다
def test_assignment_validation_errors(client, club):
    m, pid = club["manager"], club["pid"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    ids = [pid[n] for n, *_ in ROSTER]
    # 인원 부족: 새 일정에 5명만 참석
    small = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": "2026-09-20"}, headers=m).json()["id"]
    for h in club["members"][:5]:
        client.put(f"{API}/events/{small}/attendance", json={"status": "ATTEND"}, headers=h)
    r = client.post(f"{API}/events/{small}/assignments", json={"team_count": 2}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "NOT_ENOUGH_PLAYERS"

    def violate(constraints):
        return client.post(f"{API}/events/{eid}/assignments:validate", json={"team_count": 2, "constraints": constraints}, headers=m).json()

    assert violate({"lock_groups": [ids[:7]]})["violations"][0]["code"] == "LOCK_GROUP_TOO_LARGE"
    assert violate({"lock_groups": [ids[:2]], "separate_groups": [ids[:2]]})["violations"][0]["code"] == "CONSTRAINT_CONFLICT"
    assert violate({"pins": [{"player_id": p, "squad_no": 1} for p in ids[:7]]})["violations"][0]["code"] == "SQUAD_OVERFLOW"
    assert violate({"lock_groups": [[ids[0], 999999]]})["violations"][0]["code"] == "PLAYER_NOT_IN_TEAM"
    # 분할 불가: 5명·4명·3명 그룹 → 어떤 조합도 6명을 만들 수 없음 (5, 4, 3, 7, 8, 9, 12 만 가능)
    v = violate({"lock_groups": [ids[:5], ids[5:9], ids[9:12]]})
    assert not v["feasible"] and v["violations"][0]["code"] == "LOCK_PARTITION_INFEASIBLE"
    # 갈라놓기 + PIN 같은 팀 → SEPARATE_INFEASIBLE
    v = violate({"separate_groups": [ids[:2]], "pins": [{"player_id": ids[0], "squad_no": 1}, {"player_id": ids[1], "squad_no": 1}]})
    assert v["violations"][0]["code"] == "SEPARATE_INFEASIBLE"
    # 실행도 같은 코드로 차단 + details
    r = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2, "constraints": {"lock_groups": [ids[:7]]}}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "LOCK_GROUP_TOO_LARGE" and r.json()["details"]


# 검증: 13.4절 속성 검사 — 무작위 LOCK/SEPARATE/PIN 조합에서 제약이 항상 지켜진다
def test_constraints_always_honored(client, club):
    m, pid = club["manager"], club["pid"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    ids = [pid[n] for n, *_ in ROSTER]
    rng = random.Random(42)
    checked = 0
    for _ in range(8):
        shuffled = ids[:]
        rng.shuffle(shuffled)
        locks = [shuffled[:rng.randint(2, 3)], shuffled[3:5]]
        seps = [[shuffled[5], shuffled[6]]]
        pins = [{"player_id": shuffled[7], "squad_no": 1}, {"player_id": shuffled[8], "squad_no": 2}]
        body = {"team_count": 2, "strategies": ["SKILL", "BALANCED"], "constraints": {"lock_groups": locks, "separate_groups": seps, "pins": pins}}
        v = client.post(f"{API}/events/{eid}/assignments:validate", json=body, headers=m).json()
        if not v["feasible"]:
            continue
        run = client.post(f"{API}/events/{eid}/assignments", json=body, headers=m).json()
        for cand in run["candidates"]:
            squad_of = {mbr["id"]: s["squad_no"] for s in cand["squads"] for mbr in s["members"]}
            for g in locks:
                assert len({squad_of[p] for p in g}) == 1, ("LOCK 위반", g)
            assert squad_of[seps[0][0]] != squad_of[seps[0][1]], "SEPARATE 위반"
            assert squad_of[pins[0]["player_id"]] == 1 and squad_of[pins[1]["player_id"]] == 2, "PIN 위반"
            checked += 1
    assert checked >= 4


# 검증: FR-22 · FR-23 · FR-24 — 교체 후 재계산, 묶인 사람 교체 거부, 확정 → 플레이어 뷰 마스킹, 재확정 409, 직전 회차 제약
def test_swap_adopt_and_player_view(client, club):
    m, pid = club["manager"], club["pid"]
    eid, _ = _event_with_attendance(client, club)
    lock = [pid["최준용"], pid["이정현"]]
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2, "constraints": {"lock_groups": [lock]}}, headers=m).json()
    cand = run["candidates"][0]
    black, white = cand["squads"]
    a = next(mbr["id"] for mbr in black["members"] if mbr["id"] not in lock)
    b = next(mbr["id"] for mbr in white["members"] if mbr["id"] not in lock)

    # 묶인 사람 하나만 지정해도 묶음 전체가 함께 움직인다 (b 는 반대로)
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": lock[0], "player_id_b": b}]}, headers=m)
    assert r.status_code == 200, r.text
    moved = {mbr["id"]: s["squad_no"] for s in r.json()["squads"] for mbr in s["members"]}
    assert moved[lock[0]] == moved[lock[1]] == 2 and moved[b] == 1
    # 되돌리기
    client.post(f"{API}/assignments/candidates/{cand['id']}:reset", headers=m)
    # 정상 교체 → 팀이 바뀌고 수동 수정 표시
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": b}]}, headers=m)
    assert r.status_code == 200, r.text
    c2 = r.json()
    assert b in {x["id"] for x in c2["squads"][0]["members"]} and a in {x["id"] for x in c2["squads"][1]["members"]}
    assert set(c2["squads"][0]["manual_override_ids"]) == {b} and c2["metrics"]["manually_edited"] is True
    # 플레이어는 교체 불가
    assert client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": b}]}, headers=club["members"][1]).status_code == 403

    # 확정
    assert client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=club["members"][1]).status_code == 403
    r = client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m)
    assert r.status_code == 200 and r.json()["is_adopted"] is True
    assert client.get(f"{API}/events/{eid}", headers=m).json()["status"] == "CLOSED"
    assert client.get(f"{API}/events/{eid}", headers=m).json()["adopted_candidate_id"] == cand["id"]
    # 같은 run 의 다른 후보안 확정 → 409, 확정안 수정 → 409
    r = client.post(f"{API}/assignments/candidates/{run['candidates'][1]['id']}:adopt", headers=m)
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_ADOPTED"
    assert client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": b}]}, headers=m).status_code == 409

    # 플레이어 뷰: 수치·등급 마스킹, 내 팀·포지션, 문장 설명
    me = club["members"][1]
    view = client.get(f"{API}/events/{eid}/assignment/adopted", headers=me).json()
    assert view["candidate_id"] == cand["id"] and view["my_squad_no"] in (1, 2)
    assert all(s["avg_skill"] is None for s in view["squads"]) and "평균" not in view["explanation"]
    assert all("prior_overall" not in mbr and mbr["skill_grade"] is None for s in view["squads"] for mbr in s["members"])
    # 팀 상세·홈 카드용: 일정 조회에 내 팀·포지션이 붙는다
    ev = client.get(f"{API}/events/{eid}", headers=me).json()
    assert ev["my_squad_name"] in ("블랙", "화이트") and ev["adopted_candidate_id"] == cand["id"]
    mgr_view = client.get(f"{API}/events/{eid}/assignment/adopted", headers=m).json()
    assert all(s["avg_skill"] is not None for s in mgr_view["squads"])

    # 재배정(새 run) 후 확정하면 이전 확정 해제
    run2 = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    client.post(f"{API}/assignments/candidates/{run2['candidates'][2]['id']}:adopt", headers=m)
    assert client.get(f"{API}/events/{eid}/assignment/adopted", headers=m).json()["candidate_id"] == run2["candidates"][2]["id"]

    # 직전 회차 제약: 다음 일정에서 불러오기
    nxt = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": "2026-09-20"}, headers=m).json()["id"]
    lc = client.get(f"{API}/events/{nxt}/assignments/last-constraints", headers=m).json()
    assert lc == {"lock_groups": [], "separate_groups": [], "pins": []}  # 직전 회차의 마지막 run(run2)은 제약 없음
    assert client.get(f"{API}/events/{eid}/assignments/last-constraints", headers=m).json()["code"] == "NOT_FOUND"


# 검증: 홀수 인원(13명 → 7/6)도 배정되고, 한 명 이동(moves)·수동 수정 초기화(:reset)가 동작한다
def test_odd_roster_move_and_reset(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club, guests=1)  # 12 + 1 = 13명
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    cand = run["candidates"][0]
    sizes = sorted(len(s["members"]) for s in cand["squads"])
    assert sizes == [6, 7]
    assert cand["metrics"]["original_squads"]
    big = max(cand["squads"], key=lambda s: len(s["members"]))
    small = min(cand["squads"], key=lambda s: len(s["members"]))
    mover = big["members"][0]["id"]
    # 한 명을 작은 팀으로 이동 → 6/7 이 뒤집힘
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"moves": [{"player_id": mover, "to_squad_no": small["squad_no"]}]}, headers=m)
    assert r.status_code == 200, r.text
    c2 = r.json()
    moved_to = next(s for s in c2["squads"] if s["squad_no"] == small["squad_no"])
    assert mover in {x["id"] for x in moved_to["members"]} and len(moved_to["members"]) == 7
    assert mover in moved_to["manual_override_ids"] and c2["metrics"]["manually_edited"] is True
    # 5명 아래로는 못 옮긴다: 작은 팀(6명)에서 2명을 빼면 4명
    small_now = next(s for s in c2["squads"] if s["squad_no"] != small["squad_no"])
    ids = [x["id"] for x in small_now["members"]][:2]
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"moves": [{"player_id": pid, "to_squad_no": small["squad_no"]} for pid in ids]}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "INVALID_SWAP"
    # 초기화 → 원래 편성으로, 수동 표시 해제
    r = client.post(f"{API}/assignments/candidates/{cand['id']}:reset", headers=m)
    assert r.status_code == 200
    c3 = r.json()
    assert c3["metrics"]["manually_edited"] is False
    assert all(not s["manual_override_ids"] for s in c3["squads"])
    assert {frozenset(x["id"] for x in s["members"]) for s in c3["squads"]} == {frozenset(x["id"] for x in s["members"]) for s in cand["squads"]}


# 검증: 갈라놓기(SEPARATE)된 사람은 한 명만 옮길 수 없고, 갈라놓은 상대와만 맞교체할 수 있다
def test_separated_players_edit_rules(client, club):
    m, pid = club["manager"], club["pid"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    a, b = pid["최준용"], pid["이정현"]
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2, "constraints": {"separate_groups": [[a, b]]}}, headers=m).json()
    cand = run["candidates"][0]
    squad_of = {mbr["id"]: s["squad_no"] for s in cand["squads"] for mbr in s["members"]}
    assert squad_of[a] != squad_of[b]
    # 한 명 이동 → 422
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"moves": [{"player_id": a, "to_squad_no": squad_of[b]}]}, headers=m)
    assert r.status_code == 422 and "갈라놓기" in r.json()["message"]
    # 갈라놓지 않은 사람과 맞교체 → 422 (같은 팀이 되어 버림)
    other = next(x["id"] for s in cand["squads"] for x in s["members"] if s["squad_no"] == squad_of[b] and x["id"] != b)
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": other}]}, headers=m)
    assert r.status_code == 422
    # 갈라놓은 상대와 맞교체 → 200, 여전히 다른 팀
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": b}]}, headers=m)
    assert r.status_code == 200
    after = {mbr["id"]: s["squad_no"] for s in r.json()["squads"] for mbr in s["members"]}
    assert after[a] == squad_of[b] and after[b] == squad_of[a]


# 검증: 그룹 교환 — 묶음 한 명만 골라 옮겨도 묶음 전체가 이동, 평균 신장이 팀 카드에 나온다
def test_exchange_moves_whole_lock_group_and_height(client, club):
    m, pid = club["manager"], club["pid"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    lock = [pid["최준용"], pid["이정현"], pid["함지훈"]]
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2, "constraints": {"lock_groups": [lock]}}, headers=m).json()
    cand = run["candidates"][0]
    for s in cand["squads"]:
        assert s["avg_height_cm"] is not None and 150 < s["avg_height_cm"] < 210
    squad_of = {mbr["id"]: s["squad_no"] for s in cand["squads"] for mbr in s["members"]}
    src, dst = squad_of[lock[0]], 3 - squad_of[lock[0]]
    # 묶음 한 명 + 상대 팀 한 명 교환 → 묶음 3명이 통째로 넘어가고 상대 1명이 온다 (5명 최소 유지: 6명 팀에서 3명 나가고 1명 옴 → 4명이면 422)
    other = next(mbr["id"] for s in cand["squads"] for mbr in s["members"] if s["squad_no"] == dst)
    r = client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"exchanges": [{"a_player_ids": [lock[0]], "b_player_ids": [other]}]}, headers=m)
    if r.status_code == 422:
        assert "최소 5명" in r.json()["message"]
    else:
        after = {mbr["id"]: s["squad_no"] for s in r.json()["squads"] for mbr in s["members"]}
        assert all(after[p] == dst for p in lock) and after[other] == src
        assert all(p in next(s for s in r.json()["squads"] if s["squad_no"] == dst)["manual_override_ids"] for p in lock)
    # 확정 결과에 균형 점수·예상 차이·평균 신장이 포함된다 (플레이어에게도)
    client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m)
    view = client.get(f"{API}/events/{eid}/assignment/adopted", headers=club["members"][1]).json()
    assert view["total_score"] is not None and view["skill_spread"] is not None
    assert all(s["avg_height_cm"] is not None and s["avg_skill"] is None for s in view["squads"])
