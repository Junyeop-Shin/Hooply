"""고치기 화면에서 칸을 비우고 저장하면 지워진다 (docs/09 2-8).

예전에는 화면이 빈 칸을 보내지 않아(JSON 에서 키가 빠짐) 서버가 '변경 없음' 으로 받았다. 이제 화면은 비운 칸을 null 로
보낸다 — 서버가 null 을 '지우기' 로 받는지, 비울 수 없는 칸(일정 날짜 · 팀 이름)은 그대로 두는지 확인한다.
"""

from tests.test_ranking_assignment import club  # noqa: F401 — 픽스처 재사용

API = "/api/v1"


# 검증: 일정 메모 · 장소 · 응답 마감 · 시각을 null 로 보내면 지워지고, 날짜는 null 이어도 그대로다
def test_event_patch_null_clears_optional_fields(client, club):
    m, tid = club["manager"], club["team_id"]
    ev = client.post(f"{API}/teams/{tid}/events", json={
        "event_date": "2026-12-06", "start_time": "10:00", "end_time": "12:00", "venue": "서초 체육관",
        "rsvp_deadline": "2026-12-05T13:00:00Z", "memo": "회비 5,000원",
    }, headers=m).json()
    r = client.patch(f"{API}/events/{ev['id']}", json={
        "event_date": None, "venue": None, "memo": None, "rsvp_deadline": None, "start_time": None, "end_time": None,
    }, headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_date"] == "2026-12-06"
    assert body["venue"] is None and body["memo"] is None and body["rsvp_deadline"] is None
    assert body["start_time"] is None and body["end_time"] is None
    # 보내지 않은 칸은 그대로
    r = client.patch(f"{API}/events/{ev['id']}", json={"memo": "다시 적음"}, headers=m)
    assert r.json()["memo"] == "다시 적음" and r.json()["venue"] is None


# 검증: 팀 소개 · 홈 코트는 null 로 지워지고, 팀 이름 null 은 무시된다(이름은 비울 수 없다)
def test_team_patch_null_clears_description_keeps_name(client, club):
    m, tid = club["manager"], club["team_id"]
    assert client.patch(f"{API}/teams/{tid}", json={"description": "일요일 오전", "home_court": "서초"}, headers=m).status_code == 200
    r = client.patch(f"{API}/teams/{tid}", json={"name": None, "description": None, "home_court": None}, headers=m)
    assert r.status_code == 200, r.text
    team = client.get(f"{API}/teams/{tid}", headers=m).json()
    assert team["name"] and team["description"] is None and team["home_court"] is None
