"""시작 안내 — 새 가입자는 PENDING, 경로별 체크리스트는 실제 데이터로 판정하고 막힌 단계는 WAITING 과 이유를 준다."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tests.test_survey_guest_event import (  # noqa: F401 — 6명 ACTIVE 팀 픽스처 재사용
    _submit,
    _template,
    team,
)

API = "/api/v1"


def _day(n: int) -> str:
    return (datetime.now(ZoneInfo("Asia/Seoul")).date() + timedelta(days=n)).isoformat()


def _steps(client, h):
    r = client.get(f"{API}/me/tutorial", headers=h)
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()["steps"]}, r.json()


def test_new_user_starts_pending_and_can_decline_or_restart(client, signup):
    h = signup("new@t.com", name="새내기")
    me = client.get(f"{API}/me", headers=h).json()
    assert me["tutorial_state"] == "PENDING" and me["tutorial_path"] is None and me["tutorial_tips_seen"] == []
    # 안내 받기 → 경로 선택 전이라 단계가 없다
    v = client.put(f"{API}/me/tutorial", json={"state": "ACTIVE"}, headers=h).json()
    assert v["state"] == "ACTIVE" and v["path"] is None and v["steps"] == []
    v = client.put(f"{API}/me/tutorial", json={"path": "PLAYER"}, headers=h).json()
    assert [s["key"] for s in v["steps"]] == ["JOIN_TEAM", "SURVEY", "SELF_RANK", "FIRST_RSVP"]
    # 다시 시작하면 경로 선택부터
    v = client.put(f"{API}/me/tutorial", json={"state": "ACTIVE"}, headers=h).json()
    assert v["path"] is None
    # 첫 안내 기록 — 같은 id 는 한 번만, 모르는 id 는 400
    assert client.put(f"{API}/me/tutorial", json={"tip_seen": "assign"}, headers=h).json()["tips_seen"] == ["assign"]
    assert client.put(f"{API}/me/tutorial", json={"tip_seen": "assign"}, headers=h).json()["tips_seen"] == ["assign"]
    assert client.put(f"{API}/me/tutorial", json={"tip_seen": "nope"}, headers=h).status_code == 400
    assert client.put(f"{API}/me/tutorial", json={"state": "DECLINED"}, headers=h).json()["state"] == "DECLINED"


def test_player_path_waits_for_team_and_event(client, signup, team):
    h = signup("player@t.com", name="신입")
    client.put(f"{API}/me/tutorial", json={"state": "ACTIVE", "path": "PLAYER"}, headers=h)
    s, _ = _steps(client, h)
    assert s["JOIN_TEAM"]["status"] == "TODO" and s["JOIN_TEAM"]["link"] == "/teams/join"
    assert s["SELF_RANK"]["status"] == "WAITING" and s["FIRST_RSVP"]["status"] == "WAITING"

    assert client.post(f"{API}/teams/join", json={"team_code": team["code"]}, headers=h).status_code == 200
    s, _ = _steps(client, h)
    assert s["JOIN_TEAM"]["status"] == "DONE"
    assert s["SELF_RANK"]["status"] == "TODO" and s["SELF_RANK"]["link"] == f"/teams/{team['team_id']}/self-rank"
    assert s["FIRST_RSVP"]["status"] == "WAITING" and "매니저가 일정을 올리면" in s["FIRST_RSVP"]["hint"]

    day = _day(7)
    eid = client.post(f"{API}/teams/{team['team_id']}/events", json={"event_date": day, "start_time": "10:00", "end_time": "12:00"}, headers=team["manager"]).json()["id"]
    s, _ = _steps(client, h)
    assert s["FIRST_RSVP"]["status"] == "TODO" and s["FIRST_RSVP"]["link"] == f"/events/{eid}"
    # 매니저의 대리 응답은 본인 응답으로 치지 않는다
    me_pid = next(p["id"] for p in client.get(f"{API}/teams/{team['team_id']}/players", headers=team["manager"]).json()["items"] if p["display_name"] == "신입")
    client.put(f"{API}/events/{eid}/attendances/{me_pid}", json={"status": "ATTEND"}, headers=team["manager"])
    assert _steps(client, h)[0]["FIRST_RSVP"]["status"] == "TODO"
    assert client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h).status_code == 200
    s, v = _steps(client, h)
    assert s["FIRST_RSVP"]["status"] == "DONE"
    assert v["all_done"] is False  # 설문·내 위치는 아직

    assert client.put(f"{API}/teams/{team['team_id']}/self-rank", json={"level": "MID"}, headers=h).status_code == 200
    _submit(client, h, _template(client))
    assert _steps(client, h)[1]["all_done"] is True


def test_manager_path_waits_for_members_then_event(client, signup):
    h = signup("boss@t.com", name="팀장")
    client.put(f"{API}/me/tutorial", json={"state": "ACTIVE", "path": "MANAGER"}, headers=h)
    s, _ = _steps(client, h)
    assert s["CREATE_TEAM"]["status"] == "TODO" and s["INVITE"]["status"] == "WAITING" and s["FIRST_EVENT"]["status"] == "WAITING"

    t = client.post(f"{API}/teams", json={"name": "새팀"}, headers=h).json()
    s, _ = _steps(client, h)
    assert s["CREATE_TEAM"]["status"] == "DONE"
    assert s["INVITE"]["status"] == "TODO" and "팀원 1/5명" in s["INVITE"]["hint"] and s["INVITE"]["link"] == f"/teams/{t['id']}"
    assert s["FIRST_EVENT"]["status"] == "WAITING"

    for i in range(4):
        client.post(f"{API}/teams/join", json={"team_code": t["team_code"]}, headers=signup(f"u{i}@t.com", name=f"회원{i}"))
    s, _ = _steps(client, h)
    assert s["INVITE"]["status"] == "DONE" and s["FIRST_EVENT"]["status"] == "TODO"
    client.post(f"{API}/teams/{t['id']}/events", json={"event_date": _day(3)}, headers=h)
    s, _ = _steps(client, h)
    assert s["FIRST_EVENT"]["status"] == "DONE" and [k for k, x in s.items() if x["status"] != "DONE"] == ["SURVEY"]
