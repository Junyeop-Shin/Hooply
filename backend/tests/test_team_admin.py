"""팀 관리 권한 정리 (docs/09 3-7 · 3-14).

- 제외한 사람 한 명만 풀기: REMOVED → LEFT, 지금 코드로 돌아올 수 있다 (코드 재발급과 따로)
- 팀장 넘기기: 받는 사람은 매니저가 되고 팀장이 된다. 팀장만 할 수 있다
- 위임받은 매니저는 스스로 그만둘 수 있다 (마지막 매니저는 못 한다)
- 매니저가 없는 팀에 다시 들어오면 그 사람이 매니저(팀장이 팀에 없으면 팀장도)
"""

API = "/api/v1"


def _team(client, signup, tag):
    owner = signup(f"owner@{tag}.com", name="팀장")
    team = client.post(f"{API}/teams", json={"name": f"{tag}팀"}, headers=owner).json()
    members = []
    for i in range(3):
        h = signup(f"p{i}@{tag}.com", name=f"팀원{i}")
        client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=h)
        members.append(h)
    return owner, team, members


def _pid(client, h, team_id):
    return client.get(f"{API}/teams/{team_id}", headers=h).json()["my_player_id"]


def test_unremove_lets_one_person_back_with_current_code(client, signup):
    owner, team, members = _team(client, signup, "unrm")
    tid, code = team["id"], team["team_code"]
    p0, p1 = _pid(client, members[0], tid), _pid(client, members[1], tid)
    for pid in (p0, p1):
        assert client.delete(f"{API}/teams/{tid}/players/{pid}", headers=owner).status_code == 204
    removed = client.get(f"{API}/teams/{tid}/players?status=REMOVED", headers=owner).json()["items"]
    assert {p["id"] for p in removed} == {p0, p1}
    # 플레이어는 못 푼다 · 제외 상태가 아니면 400
    assert client.post(f"{API}/teams/{tid}/players/{p0}:unremove", headers=members[2]).status_code == 403
    assert client.post(f"{API}/teams/{tid}/players/{p0}:unremove", headers=owner).status_code == 200
    assert client.post(f"{API}/teams/{tid}/players/{p0}:unremove", headers=owner).status_code == 400
    # 푼 사람만 지금 코드로 돌아오고, 다른 제외자는 그대로 막힌다 · 코드는 그대로
    assert client.post(f"{API}/teams/join", json={"team_code": code}, headers=members[0]).status_code == 200
    r = client.post(f"{API}/teams/join", json={"team_code": code}, headers=members[1])
    assert r.status_code == 403 and r.json()["code"] == "REMOVED_FROM_TEAM"
    assert client.get(f"{API}/teams/{tid}", headers=owner).json()["team_code"] == code


def test_transfer_owner_and_resign(client, signup):
    owner, team, members = _team(client, signup, "own")
    tid = team["id"]
    p0, p1 = _pid(client, members[0], tid), _pid(client, members[1], tid)
    # 팀장이 아니면 넘길 수 없다 (매니저여도)
    assert client.patch(f"{API}/teams/{tid}/players/{p1}/role", json={"role": "MANAGER"}, headers=owner).status_code == 200
    r = client.post(f"{API}/teams/{tid}:transfer-owner", json={"player_id": p0}, headers=members[1])
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN_NOT_OWNER"
    # 팀장 → 팀원0: 팀원0 은 매니저가 되고 팀장이 된다. 넘긴 사람은 매니저로 남는다
    r = client.post(f"{API}/teams/{tid}:transfer-owner", json={"player_id": p0}, headers=owner)
    assert r.status_code == 200, r.text
    detail = client.get(f"{API}/teams/{tid}", headers=members[0]).json()
    assert detail["my_role"] == "MANAGER" and detail["owner"]["name"] == "팀원0"
    assert client.get(f"{API}/teams/{tid}", headers=owner).json()["my_role"] == "MANAGER"
    # 위임받은 매니저(팀원1)는 남의 역할은 못 바꾸지만 스스로 그만둘 수 있다
    assert client.patch(f"{API}/teams/{tid}/players/{p0}/role", json={"role": "PLAYER"}, headers=members[1]).status_code == 403
    assert client.patch(f"{API}/teams/{tid}/players/{p1}/role", json={"role": "PLAYER"}, headers=members[1]).status_code == 200
    assert client.get(f"{API}/teams/{tid}", headers=members[1]).json()["my_role"] == "PLAYER"


def test_rejoin_into_team_without_manager_becomes_manager(client, signup):
    owner = signup("solo@rejoin.com", name="혼자")
    team = client.post(f"{API}/teams", json={"name": "혼자팀"}, headers=owner).json()
    tid = team["id"]
    assert client.post(f"{API}/teams/{tid}:leave", headers=owner).status_code == 204
    assert client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=owner).status_code == 200
    assert client.get(f"{API}/teams/{tid}", headers=owner).json()["my_role"] == "MANAGER"
    # 매니저가 있는 팀에 새로 들어온 사람은 그대로 PLAYER
    p = signup("new@rejoin.com", name="새사람")
    client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=p)
    assert client.get(f"{API}/teams/{tid}", headers=p).json()["my_role"] == "PLAYER"


# 검증: docs/09 3-8 — 매니저는 회원 포지션을 이 팀에서만 고치고, 플레이어는 남의 것을 못 고친다. 설문 없이 본인도 고칠 수 있다
def test_manager_edits_member_positions_for_this_team_only(client, signup):
    owner, team, members = _team(client, signup, "pos")
    tid = team["id"]
    other = client.post(f"{API}/teams", json={"name": "다른팀"}, headers=owner).json()
    client.post(f"{API}/teams/join", json={"team_code": other["team_code"]}, headers=members[0])
    p0, p1 = _pid(client, members[0], tid), _pid(client, members[1], tid)
    other_p0 = _pid(client, members[0], other["id"])
    url = f"{API}/teams/{tid}/players/{p0}/positions"
    body = {"positions": [{"position": "C"}, {"position": "PF"}]}
    assert client.put(url, json=body, headers=members[1]).status_code == 403
    assert client.put(url, json={"positions": [{"position": "C"}, {"position": "C"}]}, headers=owner).status_code == 400
    r = client.put(url, json=body, headers=owner)
    assert r.status_code == 200 and r.json()["playable_positions"] == ["C", "PF"] and r.json()["primary_position"] == "C"
    # 다른 팀의 내 행은 그대로
    others = client.get(f"{API}/teams/{other['id']}/players", headers=owner).json()["items"]
    assert next(x for x in others if x["id"] == other_p0)["playable_positions"] != ["C", "PF"]
    # 설문을 안 한 본인도 고칠 수 있다
    assert client.put(f"{API}/me/positions", json={"positions": [{"position": "PG"}]}, headers=members[1]).status_code == 200
    mine = client.get(f"{API}/teams/{tid}/players", headers=owner).json()["items"]
    assert next(x for x in mine if x["id"] == p1)["playable_positions"] == ["PG"]
