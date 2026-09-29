"""전술 추천 · 이름표 API (docs/07 T2 · T5 · T6).

club 픽스처(12명 + 게스트 2명 참석)로 배정을 확정한 뒤 추천·이름표를 확인한다.
"""

from app.tactics.court import zone_of
from app.tactics.play import playability_errors
from app.tactics.presets import PRESET_LIST, PRESETS, get_play
from tests.test_ranking_assignment import _event_with_attendance, club  # noqa: F401

API = "/api/v1"


# ---------------------------------------------------------------------------
# T2 프리셋 8개
# ---------------------------------------------------------------------------


def test_presets_are_playable():
    assert len(PRESET_LIST) == 8
    assert set(PRESETS) == {"high_pnr", "horns", "weave", "pistol", "floppy", "ucla", "post_split", "zone_131"}
    for p in PRESET_LIST:
        assert playability_errors(p) == [], p.key
        assert 3 <= len(p.steps) <= 6, p.key


def test_three_point_finishes_end_outside_the_arc():
    """슈터에게 끝나는 전술은 마무리 자리가 3점 밖, 골밑 마무리는 페인트 안."""
    expect = {"horns": "three", "weave": "three", "floppy": "three", "high_pnr": "paint", "ucla": "paint", "zone_131": "paint"}
    for key, zone in expect.items():
        p = PRESETS[key]
        pos = [(s.x, s.y) for s in p.start]
        for st in p.steps:
            for a in st.actions:
                if a.to:
                    pos[a.slot - 1] = (a.to.x, a.to.y)
        last = p.steps[-1].actions[0]
        finisher = last.target if last.type == "pass" else last.slot
        assert zone_of(*pos[finisher - 1]) == zone, key


def test_get_play_accepts_prefixed_key():
    assert get_play("preset:horns") is PRESETS["horns"]
    assert get_play("horns") is PRESETS["horns"]
    assert get_play("preset:nope") is None


def test_presets_endpoint(client, signup):
    h = signup("t@t.com")
    r = client.get(f"{API}/tactics/presets", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["presets_version"] >= 1 and len(body["items"]) == 8
    assert body["items"][0]["steps"][0]["actions"][0]["type"] == "screen"
    assert client.get(f"{API}/tactics/presets").status_code == 401


# ---------------------------------------------------------------------------
# 추천 · 이름표
# ---------------------------------------------------------------------------


def _adopted_event(client, club):
    m = club["manager"]
    eid, guests = _event_with_attendance(client, club)
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    cand = run["candidates"][0]
    assert client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m).status_code == 200
    squads = client.get(f"{API}/events/{eid}/assignment/adopted", headers=m).json()["squads"]
    return eid, guests, {s["squad_no"]: [mb["id"] for mb in s["members"]] for s in squads}


def test_recommend_needs_adopted_assignment(client, club):
    eid, _ = _event_with_attendance(client, club)
    r = client.get(f"{API}/events/{eid}/tactics/recommend", headers=club["manager"])
    assert r.status_code == 404 and r.json()["code"] == "NOT_ADOPTED_YET"
    # 확정 전에도 전술판은 열린다 (이름표 칸만 없다)
    r = client.get(f"{API}/events/{eid}/tactics/preset:horns", headers=club["members"][2])
    assert r.status_code == 200 and r.json()["squads"] == []


def test_recommend_top3_and_zone_toggle(client, club):
    m = club["manager"]
    eid, guests, squads = _adopted_event(client, club)
    r = client.get(f"{API}/events/{eid}/tactics/recommend", headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["squad_no"] for s in body["squads"]] == [1, 2] and body["zone"] is False
    for sq in body["squads"]:
        assert len(sq["items"]) == 3
        fits = [it["fit"] for it in sq["items"]]
        assert fits == sorted(fits, reverse=True)
        for it in sq["items"]:
            assert get_play(it["play_key"]).defense in ("man", "any")
            ids = [s["player_id"] for s in it["slots"]]
            assert len(set(ids)) == 5 and set(ids) <= set(squads[sq["squad_no"]])
            for s in it["slots"]:
                assert 0 <= s["score"] <= 100
                assert s["alt_player_id"] is None or s["alt_player_id"] not in ids
                if s["player_id"] in guests:  # T4: 설문 없는 게스트
                    assert "설문 없음(게스트)" in s["missing_attrs"]

    # T5: 지역 수비를 켜면 zone·any 전술만 (1단계 프리셋에서는 두 개)
    r = client.get(f"{API}/events/{eid}/tactics/recommend", params={"zone": "true", "squad_no": 2}, headers=m)
    body = r.json()
    assert [s["squad_no"] for s in body["squads"]] == [2]
    assert {it["play_key"] for it in body["squads"][0]["items"]} == {"preset:zone_131", "preset:post_split"}

    # 팀원에게는 추천을 주지 않는다
    r = client.get(f"{API}/events/{eid}/tactics/recommend", headers=club["members"][3])
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN_ROLE"


def test_name_tags_save_and_visibility(client, club, signup):
    m, members = club["manager"], club["members"]
    eid, _, squads = _adopted_event(client, club)
    black = squads[1]
    url = f"{API}/events/{eid}/tactics/preset:high_pnr/slots"
    slots = [{"slot": i + 1, "player_id": pid} for i, pid in enumerate(black[:5])]

    # 팀원은 저장할 수 없다
    assert client.put(url, json={"squad_no": 1, "slots": slots}, headers=members[4]).status_code == 403
    # 다른 팀 선수 → 422, 같은 자리 두 번 → 400
    bad = [*slots[:4], {"slot": 5, "player_id": squads[2][0]}]
    r = client.put(url, json={"squad_no": 1, "slots": bad}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAYER_NOT_IN_SQUAD"
    assert r.json()["details"][0]["context"]["player_ids"] == [squads[2][0]]
    dup = [*slots[:4], {"slot": 4, "player_id": black[4]}]
    assert client.put(url, json={"squad_no": 1, "slots": dup}, headers=m).status_code == 400
    assert client.put(f"{API}/events/{eid}/tactics/preset:nope/slots", json={"squad_no": 1, "slots": slots}, headers=m).status_code == 404

    r = client.put(url, json={"squad_no": 1, "slots": slots}, headers=m)
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["can_edit"] is True
    assert [s["player_id"] for s in view["squads"][0]["slots"]] == black[:5]
    assert view["squads"][1]["slots"] == []
    assert {mb["player_id"] for mb in view["squads"][0]["members"]} == set(black)

    # T6: 참석자는 보인다
    view = client.get(f"{API}/events/{eid}/tactics/preset:high_pnr", headers=members[5])
    assert view.status_code == 200
    assert view.json()["can_edit"] is False and view.json()["my_squad_no"] in (1, 2)
    assert [s["player_id"] for s in view.json()["squads"][0]["slots"]] == black[:5]
    saved = client.get(f"{API}/events/{eid}/tactics", headers=members[5]).json()
    assert [(i["play_key"], i["squad_no"], i["filled"]) for i in saved["items"]] == [("preset:high_pnr", 1, 5)]

    # T6: 참석하지 않은 팀원은 403
    team = client.get(f"{API}/teams/{club['team_id']}", headers=m).json()
    outsider = signup("late@club.com", name="늦게온사람")
    assert client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=outsider).status_code == 200
    r = client.get(f"{API}/events/{eid}/tactics/preset:high_pnr", headers=outsider)
    assert r.status_code == 403 and r.json()["code"] == "NOT_ATTENDEE"
    assert client.get(f"{API}/events/{eid}/tactics", headers=outsider).status_code == 403

    # 다시 저장하면 통째로 바뀌고, 빈 목록이면 지워진다
    r = client.put(url, json={"squad_no": 1, "slots": slots[:2]}, headers=m)
    assert len(r.json()["squads"][0]["slots"]) == 2
    client.put(url, json={"squad_no": 1, "slots": []}, headers=m)
    assert client.get(f"{API}/events/{eid}/tactics", headers=m).json()["items"] == []
