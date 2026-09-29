"""전술 추천 · 전술판 API (docs/07 T2 · T4 · T5 · T6).

club 픽스처(12명 + 게스트 2명 참석)로 배정을 확정한 뒤 자동 추천 · 자리 배치 · 공개 범위를 확인한다.
"""

from app.tactics.court import zone_of
from app.tactics.play import playability_errors
from app.tactics.presets import PRESET_LIST, PRESETS, get_play
from tests.test_ranking_assignment import _event_with_attendance, club  # noqa: F401

API = "/api/v1"


# ---------------------------------------------------------------------------
# T2 프리셋 22개 (1단계 8개 + O5 6개 + 지역 수비 6개 + 인바운드 2개)
# ---------------------------------------------------------------------------


def test_presets_are_playable():
    assert len(PRESET_LIST) == 22
    assert set(PRESETS) == {
        "high_pnr", "horns", "weave", "pistol", "floppy", "ucla", "post_split", "zone_131",
        "spain_pnr", "horns_flare", "stagger", "hammer", "iverson_cut", "overload",
        "baseline_runner", "skip_reversal", "gap_attack", "high_low", "zone_screen_flare", "corner_entry_212",
        "box_inbound", "stack_slip",
    }
    assert sum(p.defense == "zone" for p in PRESET_LIST) == 8
    inbound = [p for p in PRESET_LIST if p.situation == "inbound"]
    assert {p.key for p in inbound} == {"box_inbound", "stack_slip"}
    assert all(p.start[p.ball - 1].y < 0 for p in inbound)  # 공을 넣는 사람은 베이스라인 뒤
    for p in PRESET_LIST:
        assert playability_errors(p) == [], p.key
        assert 3 <= len(p.steps) <= 6, p.key


def test_three_point_finishes_end_outside_the_arc():
    """슈터에게 끝나는 전술은 마무리 자리가 3점 밖, 골밑 마무리는 페인트 안."""
    expect = {
        "horns": "three", "weave": "three", "floppy": "three", "high_pnr": "paint", "ucla": "paint", "zone_131": "paint",
        "spain_pnr": "paint", "horns_flare": "three", "stagger": "three", "hammer": "three", "iverson_cut": "paint", "overload": "mid",
        "baseline_runner": "three", "skip_reversal": "three", "gap_attack": "three", "high_low": "paint",
        "zone_screen_flare": "three", "corner_entry_212": "mid", "box_inbound": "paint", "stack_slip": "paint",
    }
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
    assert body["presets_version"] >= 4 and len(body["items"]) == 22
    assert sum(it["situation"] == "inbound" for it in body["items"]) == 2
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
    # 참석 응답만 한 팀원도 확정 전이면 같은 404 (403 이 아니다)
    assert client.get(f"{API}/events/{eid}/tactics/recommend", headers=club["members"][2]).status_code == 404
    # 확정 전에도 전술판은 열린다 (이름표 칸만 없다)
    r = client.get(f"{API}/events/{eid}/tactics/preset:horns", headers=club["members"][2])
    assert r.status_code == 200 and r.json()["squads"] == []


def test_auto_recommendation_for_attendees(client, club, monkeypatch):
    from app.services import tactic_service

    # club 픽스처는 모두 같은 설문(중간 실력 윙)이라 적합도가 50~60 에 몰린다. 기준을 낮춰 추천이 나오게 한다
    monkeypatch.setattr(tactic_service, "FIT_MIN", 55.0)
    m, members = club["manager"], club["members"]
    eid, guests, squads = _adopted_event(client, club)
    r = client.get(f"{API}/events/{eid}/tactics/recommend", headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["squad_no"] for s in body["squads"]] == [1, 2] and body["zone"] is False and body["can_edit"] is True
    for sq in body["squads"]:
        assert len(sq["items"]) <= 3
        fits = [it["fit"] for it in sq["items"]]
        assert fits == sorted(fits, reverse=True) and all(f >= body["fit_min"] for f in fits)
        for it in sq["items"]:
            play = get_play(it["play_key"])
            assert play.defense in ("man", "any") and play.situation == "half_court" and it["manual"] is False  # 인바운드는 추천하지 않는다
            ids = [s["player_id"] for s in it["slots"]]
            assert len(set(ids)) == 5 and set(ids) <= set(squads[sq["squad_no"]])
            for s in it["slots"]:
                assert 0 <= s["score"] <= 100  # 매니저에게는 점수
                assert s["alt_player_id"] is None or s["alt_player_id"] not in ids
                # 예비는 같은 전술판 5명 중 다른 사람
                assert all(b["player_id"] in ids and b["player_id"] != s["player_id"] for b in s["backups"])
                assert len(s["backups"]) <= 2
                if s["player_id"] in guests:  # T4: 설문 없는 게스트
                    assert "설문 없음(게스트)" in s["missing_attrs"]
    assert any(sq["items"] for sq in body["squads"])

    # 참석자(팀원)도 추천을 본다. 자리별 점수·속성·교체 후보는 비운다
    r = client.get(f"{API}/events/{eid}/tactics/recommend", headers=members[3])
    assert r.status_code == 200
    body = r.json()
    assert body["can_edit"] is False and body["my_squad_no"] in (1, 2)
    slots = [s for sq in body["squads"] for it in sq["items"] for s in it["slots"]]
    assert slots and all(s["score"] is None and s["matched_attrs"] == [] and s["missing_attrs"] == [] and s["alt_player_id"] is None for s in slots)

    # T5: 지역 수비를 켜면 zone·any 전술만
    r = client.get(f"{API}/events/{eid}/tactics/recommend", params={"zone": "true", "squad_no": 2}, headers=m)
    body = r.json()
    assert [s["squad_no"] for s in body["squads"]] == [2]
    zone_or_any = {f"preset:{p.key}" for p in PRESET_LIST if p.defense in ("zone", "any") and p.situation == "half_court"}
    assert {it["play_key"] for it in body["squads"][0]["items"]} <= zone_or_any


def test_recommendation_respects_fit_threshold(client, club, monkeypatch):
    from app.services import tactic_service

    eid, _, _ = _adopted_event(client, club)
    # 기본 기준(75)이면 모두 같은 설문인 평범한 팀에는 추천이 없다
    body = client.get(f"{API}/events/{eid}/tactics/recommend", headers=club["manager"]).json()
    assert body["fit_min"] == tactic_service.FIT_MIN and all(sq["items"] == [] for sq in body["squads"])
    monkeypatch.setattr(tactic_service, "FIT_MIN", 0.0)
    body = client.get(f"{API}/events/{eid}/tactics/recommend", headers=club["manager"]).json()
    assert all(len(sq["items"]) == 3 for sq in body["squads"])


def test_board_lineup_override_and_visibility(client, club, signup):
    m, members = club["manager"], club["members"]
    eid, _, squads = _adopted_event(client, club)
    black = squads[1]
    board = f"{API}/events/{eid}/tactics/preset:high_pnr"
    url = f"{board}/slots"

    # 전술판은 저장하지 않아도 추천 배치로 채워져 있다
    view = client.get(board, headers=members[5]).json()
    auto = view["squads"][0]["lineup"]
    assert auto["manual"] is False and len(auto["slots"]) == 5 and view["can_edit"] is False
    assert all(s["score"] is None for s in auto["slots"])

    slots = [{"slot": i + 1, "player_id": pid} for i, pid in enumerate(black[:5])]
    # 팀원은 저장할 수 없다
    assert client.put(url, json={"squad_no": 1, "slots": slots}, headers=members[4]).status_code == 403
    # 다른 팀 선수 → 422, 같은 자리 두 번 → 400, 다섯 자리가 아니면 400
    bad = [*slots[:4], {"slot": 5, "player_id": squads[2][0]}]
    r = client.put(url, json={"squad_no": 1, "slots": bad}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAYER_NOT_IN_SQUAD"
    assert r.json()["details"][0]["context"]["player_ids"] == [squads[2][0]]
    dup = [*slots[:4], {"slot": 4, "player_id": black[4]}]
    assert client.put(url, json={"squad_no": 1, "slots": dup}, headers=m).status_code == 400
    assert client.put(url, json={"squad_no": 1, "slots": slots[:3]}, headers=m).status_code == 400
    assert client.put(f"{API}/events/{eid}/tactics/preset:nope/slots", json={"squad_no": 1, "slots": slots}, headers=m).status_code == 404

    # 매니저가 자리를 바꿔 저장하면 전술판·추천 모두 그 배치 (manual)
    r = client.put(url, json={"squad_no": 1, "slots": slots}, headers=m)
    assert r.status_code == 200, r.text
    lu = r.json()["squads"][0]["lineup"]
    assert lu["manual"] is True and [s["player_id"] for s in lu["slots"]] == black[:5]
    view = client.get(board, headers=members[5]).json()
    assert [s["player_id"] for s in view["squads"][0]["lineup"]["slots"]] == black[:5]
    rec = client.get(f"{API}/events/{eid}/tactics/recommend", headers=m).json()
    for it in rec["squads"][0]["items"]:
        if it["play_key"] == "preset:high_pnr":
            assert it["manual"] is True

    # 빈 목록 → 추천 배치로 되돌린다
    r = client.put(url, json={"squad_no": 1, "slots": []}, headers=m)
    assert r.json()["squads"][0]["lineup"]["manual"] is False

    # T6: 참석하지 않은 팀원은 403
    team = client.get(f"{API}/teams/{club['team_id']}", headers=m).json()
    outsider = signup("late@club.com", name="늦게온사람")
    assert client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=outsider).status_code == 200
    for path in (board, f"{API}/events/{eid}/tactics/recommend"):
        r = client.get(path, headers=outsider)
        assert r.status_code == 403 and r.json()["code"] == "NOT_ATTENDEE"
