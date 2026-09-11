"""게스트 기록 본인 확인 병합 — 같은 이름의 회원이 가입하면 홈에 확인 카드가 뜨고, 확인하면 기록이 넘어온다 / 거절하면 다시 묻지 않는다."""

API = "/api/v1"


def _team_with_guest(client, signup):
    """5명 팀(ACTIVE) + 지난 일정에 게스트 '게스트 허웅' 참석 → (매니저 헤더, 팀 코드, 게스트 id, 일정 id)."""
    m = signup("mgr@claim.com", name="매니저")
    team = client.post(f"{API}/teams", json={"name": "확인팀"}, headers=m).json()
    for i in range(4):
        client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=signup(f"p{i}@claim.com", name=f"팀원{i}"))
    eid = client.post(f"{API}/teams/{team['id']}/events", json={"event_date": "2026-08-30", "start_time": "10:00", "end_time": "12:00"}, headers=m).json()["id"]
    g = client.post(f"{API}/events/{eid}/guests", json={"display_name": "게스트 허웅", "skill_grade": 3, "playable_positions": ["SG"], "force_new": True}, headers=m).json()
    return m, team["team_code"], g["player"]["id"], eid


def test_claim_confirm_merges_records(client, signup):
    m, code, gid, eid = _team_with_guest(client, signup)
    # 이름이 다른 회원에게는 뜨지 않는다
    other = signup("other@claim.com", name="서장훈")
    client.post(f"{API}/teams/join", json={"team_code": code}, headers=other)
    assert client.get(f"{API}/me/guest-claims", headers=other).json()["items"] == []
    # 같은 이름("허웅" ≒ "게스트 허웅")의 회원이 가입하면 확인 카드가 뜬다
    me = signup("hw@claim.com", name="허웅")
    client.post(f"{API}/teams/join", json={"team_code": code}, headers=me)
    items = client.get(f"{API}/me/guest-claims", headers=me).json()["items"]
    assert len(items) == 1 and items[0]["guest"]["id"] == gid and items[0]["events_attended"] == 1 and items[0]["team_name"] == "확인팀"
    # 남의 게스트를 가져가려 하면 403 (이름 불일치)
    assert client.post(f"{API}/players/{gid}:claim", json={"accept": True}, headers=other).status_code == 403
    # 확인 → 병합: 목록이 비고, 내 통계에 게스트 시절 참석이 합산되며, 게스트 행은 병합 상태
    r = client.post(f"{API}/players/{gid}:claim", json={"accept": True}, headers=me)
    assert r.status_code == 200 and r.json()["items"] == []
    pid = items[0]["member_player_id"]
    assert client.get(f"{API}/players/{pid}/stats", headers=me).json()["events_attended"] == 1
    att = client.get(f"{API}/events/{eid}/attendances", headers=m).json()["items"]
    assert not any(a["player"]["id"] == gid and a["player"]["kind"] == "GUEST" and a["status"] == "ATTEND" and a["player"].get("merged") for a in att)
    # 두 번째 확인은 이미 병합됨
    assert client.post(f"{API}/players/{gid}:claim", json={"accept": True}, headers=me).status_code == 409


def test_claim_decline_is_remembered(client, signup):
    _, code, gid, _ = _team_with_guest(client, signup)
    me = signup("hw2@claim.com", name="허웅")
    client.post(f"{API}/teams/join", json={"team_code": code}, headers=me)
    assert len(client.get(f"{API}/me/guest-claims", headers=me).json()["items"]) == 1
    r = client.post(f"{API}/players/{gid}:claim", json={"accept": False}, headers=me)
    assert r.status_code == 200 and r.json()["items"] == []
    assert client.get(f"{API}/me/guest-claims", headers=me).json()["items"] == []  # 다시 묻지 않는다
    # 매니저 병합 경로는 여전히 살아 있다 (게스트는 미병합 상태)
    pl = client.get(f"{API}/teams/{client.get(f'{API}/me/teams', headers=me).json()['items'][0]['team_id']}/players?kind=GUEST", headers=me).json()["items"]
    assert any(p["id"] == gid for p in pl)
