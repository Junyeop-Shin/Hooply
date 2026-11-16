"""확정한 팀 고치기 · 게스트 이름 자동완성 (docs/09 사용성 점검 1장).

- 확정 뒤 참석 변경은 매니저만: 팀원의 게스트 등록은 422 RSVP_CLOSED, 매니저는 계속 등록할 수 있다
- 확정 뒤 참석으로 바뀐 사람은 "아직 팀 없음" + 추천 팀 → `adopted:add` 로 넣는다. 다른 사람의 팀은 그대로
- 불참 처리 · 게스트 참석 취소 → 확정 팀에서도 빠진다 (쿼터 기록 전까지)
- 확정안도 옮기기 · 맞바꾸기 가능, 같은 실행 안에서 확정을 옮길 수 있다
- 게스트 자동완성은 팀 전체 게스트에서 이름 앞부분(받침 전 글자 포함)으로, 정보 수정은 초대한 사람 · 매니저만
"""

from tests.test_ranking_assignment import (  # noqa: F401 — 픽스처 재사용
    _event_with_attendance,
    club,
)

API = "/api/v1"


def _lineups(black_ids, white_ids):
    return [{"player_id": p, "side": "BLACK"} for p in black_ids] + [{"player_id": p, "side": "WHITE"} for p in white_ids]


def _adopt(client, club, eid, constraints=None):
    m = club["manager"]
    body = {"team_count": 2, **({"constraints": constraints} if constraints else {})}
    run = client.post(f"{API}/events/{eid}/assignments", json=body, headers=m).json()
    cand = run["candidates"][0]
    assert client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m).status_code == 200
    return run, cand


def _adopted(client, eid, h):
    r = client.get(f"{API}/events/{eid}/assignment/adopted", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _squad_of(view, pid):
    return next((s["squad_no"] for s in view["squads"] if any(m["id"] == pid for m in s["members"])), None)


def _sizes(view):
    return [len(s["members"]) for s in view["squads"]]


# 검증: 확정 뒤 매니저가 부른 게스트는 팀 없음 + 추천 팀으로 뜨고, 넣으면 그 팀에만 더해진다. 팀원은 확정 뒤 게스트를 못 부른다
def test_late_guest_after_adoption_goes_to_recommended_team(client, club):
    m, player = club["manager"], club["members"][1]
    eid, _ = _event_with_attendance(client, club, guests=0)
    _, cand = _adopt(client, club, eid)
    before = {s["squad_no"]: {x["id"] for x in s["members"]} for s in cand["squads"]}
    assert client.get(f"{API}/events/{eid}", headers=m).json()["rsvp_open"] is False

    r = client.post(f"{API}/events/{eid}/guests", json={"display_name": "늦은게스트"}, headers=player)
    assert r.status_code == 422 and r.json()["code"] == "RSVP_CLOSED"
    r = client.post(f"{API}/events/{eid}/guests", json={"display_name": "늦은게스트", "skill_grade": 4}, headers=m)
    assert r.status_code == 201, r.text
    gid = r.json()["player"]["id"]

    view = _adopted(client, eid, m)
    assert view["editable"] is True
    [u] = view["unassigned"]
    assert u["player"]["id"] == gid and u["allowed_squad_nos"] == [1, 2] and u["recommended_squad_no"] in (1, 2)
    # 팀원에게는 고칠 거리도, 팀 없는 사람 목록도 보이지 않는다
    pv = _adopted(client, eid, player)
    assert pv["editable"] is False and pv["unassigned"] == []
    assert client.post(f"{API}/events/{eid}/assignment/adopted:add", json={"player_id": gid, "squad_no": 1}, headers=player).status_code == 403

    to = u["recommended_squad_no"]
    r = client.post(f"{API}/events/{eid}/assignment/adopted:add", json={"player_id": gid, "squad_no": to}, headers=m)
    assert r.status_code == 200, r.text
    after = r.json()
    assert _squad_of(after, gid) == to and after["unassigned"] == [] and sorted(_sizes(after)) == [6, 7]
    for s in after["squads"]:  # 다른 사람의 팀은 그대로
        assert {x["id"] for x in s["members"]} - {gid} == before[s["squad_no"]]
    assert gid in next(s for s in after["squads"] if s["squad_no"] == to)["manual_override_ids"]
    # 이미 팀에 있으면 다시 못 넣는다 · 참석이 아닌 사람도 못 넣는다
    r = client.post(f"{API}/events/{eid}/assignment/adopted:add", json={"player_id": gid, "squad_no": to}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "INVALID_SWAP"


# 검증: 확정 뒤 불참 처리 · 게스트 참석 취소는 확정 팀에서도 빠지고, 다시 참석으로 바꾸면 사람이 적은 팀이 추천된다
def test_absent_after_adoption_drops_from_team_and_back(client, club):
    m = club["manager"]
    eid, gids = _event_with_attendance(client, club, guests=2)
    _, cand = _adopt(client, club, eid)
    member = next(x["id"] for x in cand["squads"][0]["members"] if x["kind"] == "MEMBER")
    assert client.put(f"{API}/events/{eid}/attendances/{member}", json={"status": "ABSENT"}, headers=m).status_code == 200
    view = _adopted(client, eid, m)
    assert _squad_of(view, member) is None and _sizes(view) == [len(cand["squads"][0]["members"]) - 1, len(cand["squads"][1]["members"])]
    assert view["unassigned"] == []

    # 게스트 참석 취소도 확정 팀에서 빠진다
    guest = gids[1]
    assert client.delete(f"{API}/events/{eid}/guests/{guest}", headers=m).status_code == 204
    assert _squad_of(_adopted(client, eid, m), guest) is None

    # 다시 참석 → 팀 없음, 인원이 가장 적은 팀이 추천된다
    assert client.put(f"{API}/events/{eid}/attendances/{member}", json={"status": "ATTEND"}, headers=m).status_code == 200
    view = _adopted(client, eid, m)
    [u] = view["unassigned"]
    smallest = min(view["squads"], key=lambda s: len(s["members"]))["squad_no"]
    if len({len(s["members"]) for s in view["squads"]}) > 1:
        assert u["recommended_squad_no"] == smallest


# 검증: 묶은 사람이 다시 참석하면 묶음 상대의 팀에만 넣을 수 있다
def test_add_back_respects_lock_group(client, club):
    m, pid = club["manager"], club["pid"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    a, b = pid["함지훈"], pid["정영삼"]
    _, cand = _adopt(client, club, eid, constraints={"lock_groups": [[a, b]]})
    sq_b = next(s["squad_no"] for s in cand["squads"] if any(x["id"] == b for x in s["members"]))
    other = 3 - sq_b
    client.put(f"{API}/events/{eid}/attendances/{a}", json={"status": "ABSENT"}, headers=m)
    client.put(f"{API}/events/{eid}/attendances/{a}", json={"status": "ATTEND"}, headers=m)
    [u] = _adopted(client, eid, m)["unassigned"]
    assert u["allowed_squad_nos"] == [sq_b] and u["recommended_squad_no"] == sq_b and "묶은" in u["note"]
    r = client.post(f"{API}/events/{eid}/assignment/adopted:add", json={"player_id": a, "squad_no": other}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "INVALID_SWAP"
    assert client.post(f"{API}/events/{eid}/assignment/adopted:add", json={"player_id": a, "squad_no": sq_b}, headers=m).status_code == 200


# 검증: 쿼터 기록이 생기면 확정 팀은 잠긴다 — 넣기 422, 불참 처리해도 팀은 그대로, 매니저 뷰 editable=false
def test_adopted_locked_after_quarters(client, club):
    m = club["manager"]
    eid, _gids = _event_with_attendance(client, club, guests=1)
    _, cand = _adopt(client, club, eid)
    sq = cand["squads"]
    black, white = [x["id"] for x in sq[0]["members"][:5]], [x["id"] for x in sq[1]["members"][:5]]
    r = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [{"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": _lineups(black, white)}]}, headers=m)
    assert r.status_code == 200, r.text
    leaver = sq[0]["members"][-1]["id"]
    client.put(f"{API}/events/{eid}/attendances/{leaver}", json={"status": "ABSENT"}, headers=m)
    view = _adopted(client, eid, m)
    assert view["editable"] is False and _squad_of(view, leaver) == 1
    r = client.post(f"{API}/events/{eid}/guests", json={"display_name": "기록뒤게스트"}, headers=m)
    gid = r.json()["player"]["id"]
    r = client.post(f"{API}/events/{eid}/assignment/adopted:add", json={"player_id": gid, "squad_no": 1}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "ASSIGNMENT_LOCKED"


# 검증: 자동완성 — 팀 전체 게스트에서 이름 앞부분(받침 전 글자 포함), 최근 온 순, 이미 참석한 게스트 제외, 등급은 볼 수 있는 사람에게만
def test_guest_suggest_prefix_recent_and_masking(client, club):
    m, inviter, other = club["manager"], club["members"][1], club["members"][2]
    tid = club["team_id"]
    e1 = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-11-01"}, headers=m).json()["id"]
    e2 = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-11-08"}, headers=m).json()["id"]
    e3 = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-11-15"}, headers=m).json()["id"]
    sjy = client.post(f"{API}/events/{e1}/guests", json={"display_name": "신준엽", "skill_grade": 4, "height_cm": 180}, headers=inviter).json()["player"]["id"]
    client.post(f"{API}/events/{e1}/guests", json={"display_name": "김신"}, headers=inviter)
    sdy = client.post(f"{API}/events/{e2}/guests", json={"display_name": "게스트 신동엽"}, headers=other).json()["player"]["id"]
    # 앞으로 있을 일정에 미리 등록한 것은 '지난번' 으로 세지 않는다 (순서도 바뀌지 않는다)
    future = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2099-01-04"}, headers=m).json()["id"]
    assert client.post(f"{API}/events/{future}/guests", json={"display_name": "신준엽", "existing_player_id": sjy}, headers=inviter).status_code in (200, 201)

    def suggest(eid, q, h):
        r = client.get(f"{API}/events/{eid}/guests/suggest", params={"q": q}, headers=h)
        assert r.status_code == 200, r.text
        return r.json()["items"]

    items = suggest(e3, "시", other)  # 받침 전 글자도 잡힌다 · '게스트' 접두어 무시 · '김신' 은 앞부분이 아니라 빠진다
    assert [i["player"]["id"] for i in items] == [sdy, sjy]  # 최근에 온 순 (11/8 → 11/1)
    by_id = {i["player"]["id"]: i for i in items}
    assert by_id[sjy]["last_attended"] == "2026-11-01" and by_id[sjy]["attended_count"] == 1
    # 남이 부른 게스트: 고른 등급도, 등급 글자도 안 보이고 고칠 수 없다
    assert by_id[sjy]["guest_grade"] is None and by_id[sjy]["can_edit"] is False and by_id[sjy]["player"]["skill_grade"] is None
    mine = {i["player"]["id"]: i for i in suggest(e3, "신준", inviter)}
    assert mine[sjy]["guest_grade"] == 4 and mine[sjy]["can_edit"] is True and mine[sjy]["player"]["height_cm"] == 180
    mgr = {i["player"]["id"]: i for i in suggest(e3, "신", m)}
    assert mgr[sjy]["guest_grade"] == 4 and mgr[sjy]["player"]["skill_grade"] is not None
    # 이 일정에 이미 참석인 게스트는 빠진다
    assert sjy not in {i["player"]["id"] for i in suggest(e1, "신", m)}
    assert client.get(f"{API}/events/{e3}/guests/suggest", params={"q": ""}, headers=m).status_code == 400


# 검증: 다시 초대하며 바꾼 정보는 초대한 사람 · 매니저만 반영된다. 등급을 비워 보내면 매니저가 고친 등급이 그대로 남는다
def test_reinvite_does_not_overwrite_without_permission(client, club):
    m, inviter, other = club["manager"], club["members"][1], club["members"][2]
    tid = club["team_id"]
    e1, e2, e3, e4 = (client.post(f"{API}/teams/{tid}/events", json={"event_date": d}, headers=m).json()["id"] for d in ("2026-11-01", "2026-11-08", "2026-11-15", "2026-11-22"))
    gid = client.post(f"{API}/events/{e1}/guests", json={"display_name": "신준엽", "skill_grade": 4, "height_cm": 180, "playable_positions": ["SG"]}, headers=inviter).json()["player"]["id"]

    # 다른 팀원이 다시 초대하며 등급 · 키 · 포지션을 바꿔 보내도 기록만 이어 붙는다
    r = client.post(f"{API}/events/{e2}/guests", json={"display_name": "신준엽", "existing_player_id": gid, "skill_grade": 1, "height_cm": 150, "playable_positions": ["C"]}, headers=other)
    assert r.status_code == 201, r.text
    assert r.json()["player"]["id"] == gid and r.json()["player"]["height_cm"] == 180 and r.json()["player"]["playable_positions"] == ["SG"]
    rows = client.get(f"{API}/events/{e2}/attendances", headers=m).json()["items"]
    assert next(a for a in rows if a["player"]["id"] == gid)["guest_grade"] == 4  # 매니저(고칠 수 있는 사람)에게만 실린다

    # 매니저가 등급을 2로 고친다 → 초대한 사람이 등급을 비워 다시 초대하면 2가 남는다 (예전 사본으로 4로 돌아가지 않는다)
    r = client.patch(f"{API}/events/{e2}/guests/{gid}", json={"skill_grade": 2}, headers=m)
    assert r.status_code == 200 and r.json()["guest_grade"] == 2
    r = client.post(f"{API}/events/{e3}/guests", json={"display_name": "신준엽", "existing_player_id": gid}, headers=inviter)
    assert r.status_code == 201 and r.json()["guest_grade"] == 2
    # 초대한 사람이 직접 바꾸면 반영된다
    r = client.post(f"{API}/events/{e4}/guests", json={"display_name": "신준엽", "existing_player_id": gid, "skill_grade": 5, "height_cm": 182}, headers=inviter)
    assert r.status_code == 201 and r.json()["guest_grade"] == 5 and r.json()["player"]["height_cm"] == 182
