"""참석 규칙 정리 (docs/09 2-1 · 2-2).

- 경기 기록에 출전한 사람은 참석으로 맞춘다 — 응답을 안 했거나 불참이었어도. 참석인데 안 뛴 사람은 그대로 둔다(화면이 묻는다)
- 미리 마감한 응답은 팀 확정 전 · 마감 시각 전이면 다시 받을 수 있고, 마감을 앞으로 늦춰도 다시 열린다
"""

from tests.test_adopted_edit import _adopt, _lineups
from tests.test_ranking_assignment import _event_with_attendance, club  # noqa: F401 — 픽스처 재사용

API = "/api/v1"


def _att(client, eid, h):
    return {a["player"]["id"]: a for a in client.get(f"{API}/events/{eid}/attendances", headers=h).json()["items"]}


# 검증: 출전 기록이 있는 미응답 · 불참자는 참석이 되고(매니저가 대신 바꾼 것으로), 참석인데 안 뛴 사람은 참석 그대로
def test_quarter_save_marks_players_who_played_as_attending(client, club):
    m, tid = club["manager"], club["team_id"]
    eid = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-09-13"}, headers=m).json()["id"]
    ids = sorted(_att(client, eid, m))
    assert len(ids) >= 12
    for pid in ids[:10]:
        assert client.put(f"{API}/events/{eid}/attendances/{pid}", json={"status": "ATTEND"}, headers=m).status_code == 200
    late, no_show_but_played = ids[10], ids[11]          # 응답 안 함(PENDING) · 불참이라고 했지만 와서 뜀
    assert client.put(f"{API}/events/{eid}/attendances/{no_show_but_played}", json={"status": "ABSENT"}, headers=m).status_code == 200
    black, white = [*ids[:4], late], [*ids[4:8], no_show_but_played]
    r = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [
        {"quarter_no": 1, "black_score": 10, "white_score": 8, "duration_min": 8, "lineups": _lineups(black, white)},
    ]}, headers=m)
    assert r.status_code == 200, r.text

    att = _att(client, eid, m)
    assert att[late]["status"] == "ATTEND" and att[no_show_but_played]["status"] == "ATTEND"
    assert att[late]["registered_by_name"]  # 매니저가 대신 바꾼 것으로 남는다
    assert att[ids[8]]["status"] == "ATTEND" and att[ids[9]]["status"] == "ATTEND"  # 안 뛰었어도 서버는 바꾸지 않는다
    assert client.get(f"{API}/events/{eid}", headers=m).json()["attend_count"] == 12


# 검증: 미리 마감 → 다시 받기(팀원이 다시 응답 가능). 마감 시각이 지났으면 막고, 마감을 늦추면 다시 열린다
def test_reopen_rsvp_before_adoption(client, club):
    m, tid, player = club["manager"], club["team_id"], club["members"][1]
    eid = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-12-20"}, headers=m).json()["id"]
    assert client.post(f"{API}/events/{eid}/rsvp:close", headers=m).status_code == 200
    r = client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=player)
    assert r.status_code == 422 and r.json()["code"] == "RSVP_CLOSED"
    assert client.post(f"{API}/events/{eid}/rsvp:reopen", headers=player).status_code == 403  # 매니저만
    r = client.post(f"{API}/events/{eid}/rsvp:reopen", headers=m)
    assert r.status_code == 200 and r.json()["status"] == "OPEN" and r.json()["rsvp_open"] is True
    assert client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=player).status_code == 200
    assert client.post(f"{API}/events/{eid}/rsvp:reopen", headers=m).status_code == 400  # 열려 있는 일정

    # 마감 시각이 지난 일정: 다시 받기는 막고, 마감을 앞으로 늦추면 다시 열린다
    assert client.patch(f"{API}/events/{eid}", json={"rsvp_deadline": "2026-01-01T00:00:00Z"}, headers=m).status_code == 200
    assert client.post(f"{API}/events/{eid}/rsvp:close", headers=m).status_code == 200
    r = client.post(f"{API}/events/{eid}/rsvp:reopen", headers=m)
    assert r.status_code == 400 and "마감" in r.json()["message"]
    r = client.patch(f"{API}/events/{eid}", json={"rsvp_deadline": "2099-12-19T13:00:00Z"}, headers=m)
    assert r.status_code == 200 and r.json()["status"] == "OPEN" and r.json()["rsvp_open"] is True
    # 메모만 고치면 상태는 그대로
    assert client.post(f"{API}/events/{eid}/rsvp:close", headers=m).status_code == 200
    assert client.patch(f"{API}/events/{eid}", json={"memo": "회비"}, headers=m).json()["status"] == "CLOSED"


# 검증: 팀을 확정한 일정은 다시 받을 수 없고, 마감을 늦춰도 마감 그대로 (확정 뒤 참석 변경은 매니저만)
def test_reopen_blocked_after_adoption(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club, guests=0)
    _adopt(client, club, eid)
    r = client.post(f"{API}/events/{eid}/rsvp:reopen", headers=m)
    assert r.status_code == 400 and "확정" in r.json()["message"]
    r = client.patch(f"{API}/events/{eid}", json={"rsvp_deadline": "2099-12-19T13:00:00Z"}, headers=m)
    assert r.status_code == 200 and r.json()["status"] == "CLOSED"
