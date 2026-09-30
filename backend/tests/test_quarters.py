"""쿼터 기록(F8) · 잔차 기반 실력 갱신(F10, 9.2절) · 롤백(13.2절 2항) · 첫 2회 게이트(13.2절 1항).

시나리오: 12명 팀(club 픽스처)에서 일정을 열고 12명이 참석 → 매니저가 쿼터를 기록한다.
같은 라인업으로 세 회차를 기록해 첫 두 회차는 지표에 반영되지 않고 세 번째부터 반영되는지,
쿼터를 지우면 값이 정확히 되돌아가는지 확인한다.
"""

import pytest

from tests.test_ranking_assignment import ROSTER, club  # noqa: F401 — 픽스처 재사용

API = "/api/v1"


def _event(client, club, date):
    m = club["manager"]
    eid = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": date}, headers=m).json()["id"]
    for h in club["members"]:
        client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h)
    return eid


def _lineups(club, black_names, white_names):
    pid = club["pid"]
    return [{"player_id": pid[n], "side": "BLACK"} for n in black_names] + [{"player_id": pid[n], "side": "WHITE"} for n in white_names]


def _skills(client, club):
    cards = client.get(f"{API}/teams/{club['team_id']}/players?sort=skill", headers=club["manager"]).json()["items"]
    return {c["display_name"]: (float(c["skill_overall"]), float(c["prior_overall"]), c["quarters_played"], float(c["skill_confidence"])) for c in cards}


TOP5 = [n for n, *_ in ROSTER[:5]]  # 최준용 이정현 함지훈 이규섭 양희승
BOT5 = [n for n, *_ in ROSTER[7:12]]  # 김진 신동파 라건아 김단비 박지수


@pytest.fixture
def event(client, club):
    return _event(client, club, "2026-09-13")


# 검증: FR-25 — 사이드별 5명 검증(400 INVALID_LINEUP_SIZE), 팀 밖 참가자 422, 중복 quarter_no 409, 마진 시간 정규화, 권한
def test_quarter_validation_and_margins(client, club, event):
    m, p1 = club["manager"], club["members"][1]
    good = _lineups(club, TOP5, BOT5)
    # 블랙 4명
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": good[1:]}, headers=m)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"  # pydantic: 10명 미만
    bad = good[:4] + good[5:] + [dict(good[9], player_id=club["pid"]["정영삼"], side="WHITE")]
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": bad}, headers=m)
    assert r.status_code == 400 and r.json()["code"] == "INVALID_LINEUP_SIZE" and "블랙 팀 4명" in r.json()["message"]
    # 팀 밖 id
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": good[:-1] + [{"player_id": 999999, "side": "WHITE"}]}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAYER_NOT_IN_TEAM"
    # 플레이어는 기록 불가
    assert client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": good}, headers=p1).status_code == 403

    # 쿼터 길이는 1~10분만 받는다 (기본 8분)
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 1, "white_score": 0, "duration_min": 11, "lineups": good}, headers=m)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    assert client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 1, "white_score": 0, "duration_min": 0, "lineups": good}, headers=m).status_code == 400
    # 정상 — 6분 쿼터, 블랙 12:9 → raw +3, 정규화 5.0 (블랙) / −5.0 (화이트)
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 12, "white_score": 9, "duration_min": 6, "lineups": good}, headers=m)
    assert r.status_code == 201, r.text
    q = r.json()
    assert q["duration_min"] == 6
    black = [x for x in q["lineups"] if x["side"] == "BLACK"]
    white = [x for x in q["lineups"] if x["side"] == "WHITE"]
    assert len(black) == 5 and all(x["raw_margin"] == 3 and float(x["normalized_margin"]) == 5.0 for x in black)
    assert all(x["raw_margin"] == -3 and float(x["normalized_margin"]) == -5.0 for x in white)
    # 길이를 생략하면 기본 8분
    assert client.patch(f"{API}/quarters/{q['id']}", json={"duration_min": 10}, headers=m).json()["duration_min"] == 10
    # 중복 → 409
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 1, "white_score": 0, "lineups": good}, headers=m)
    assert r.status_code == 409 and r.json()["code"] == "QUARTER_EXISTS"
    # 일정은 DONE, 조회 요약
    assert client.get(f"{API}/events/{event}", headers=m).json()["status"] == "DONE"
    lst = client.get(f"{API}/events/{event}/quarters", headers=p1).json()
    assert lst["summary"] == {**lst["summary"], "quarter_count": 1, "black_total": 12, "white_total": 9, "black_wins": 1, "white_wins": 0}
    assert all(c["quarters"] == 1 for c in lst["summary"]["per_player"]) and len(lst["summary"]["per_player"]) == 10
    # 수정: 스코어 뒤집기 → 마진 재계산
    r = client.patch(f"{API}/quarters/{q['id']}", json={"black_score": 5, "white_score": 15}, headers=m)
    assert r.status_code == 200 and all(x["raw_margin"] == -10 for x in r.json()["lineups"] if x["side"] == "BLACK")
    assert client.patch(f"{API}/quarters/{q['id']}", json={"black_score": 1}, headers=p1).status_code == 403
    # 삭제 → 쿼터 0 → 일정 CLOSED
    assert client.delete(f"{API}/quarters/{q['id']}", headers=m).status_code == 204
    assert client.get(f"{API}/events/{event}", headers=m).json()["status"] == "CLOSED"
    assert client.get(f"{API}/events/{event}", headers=m).json()["quarter_count"] == 0


# 검증: PUT 일괄 저장 — 생성/수정/삭제 개수, quarter_no 중복 400
def test_bulk_save(client, club, event):
    m = club["manager"]
    good = _lineups(club, TOP5, BOT5)
    mk = lambda no, b, w: {"quarter_no": no, "black_score": b, "white_score": w, "duration_min": 10, "lineups": good}
    r = client.put(f"{API}/events/{event}/quarters", json={"quarters": [mk(1, 10, 8), mk(2, 7, 9), mk(3, 11, 11)]}, headers=m)
    assert r.status_code == 200 and r.json() == {"created": 3, "updated": 0, "deleted": 0}
    r = client.put(f"{API}/events/{event}/quarters", json={"quarters": [mk(1, 10, 8), mk(2, 12, 9)]}, headers=m)
    assert r.json() == {"created": 0, "updated": 2, "deleted": 1}
    lst = client.get(f"{API}/events/{event}/quarters", headers=m).json()
    assert [q["quarter_no"] for q in lst["items"]] == [1, 2] and lst["summary"]["black_total"] == 22
    r = client.put(f"{API}/events/{event}/quarters", json={"quarters": [mk(1, 1, 0), mk(1, 2, 0)]}, headers=m)
    assert r.status_code == 400
    assert client.get(f"{API}/events/{event}", headers=m).json()["quarter_count"] == 2


# 검증: 13.2절 1항 첫 2회 게이트, 9.2절 잔차 갱신 방향, 13.2절 2항 삭제 롤백(값이 정확히 되돌아감)
def test_rating_warmup_update_and_rollback(client, club):
    m = club["manager"]
    good = _lineups(club, TOP5, BOT5)  # 블랙 = 상위 5, 화이트 = 하위 5
    before = _skills(client, club)
    assert all(v[0] == v[1] and v[2] == 0 for v in before.values())  # 쿼터 없음: skill = prior

    # 1·2회차: 하위 팀(화이트)이 크게 이겨도 지표는 그대로 (마진·출전 수만 기록)
    for date in ("2026-09-06", "2026-09-13"):
        eid = _event(client, club, date)
        r = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [{"quarter_no": n, "black_score": 5, "white_score": 20, "lineups": good} for n in (1, 2)]}, headers=m)
        assert r.status_code == 200, r.text
    after_warmup = _skills(client, club)
    for name in TOP5 + BOT5:
        assert after_warmup[name][0] == before[name][0], name  # skill 변화 없음
        assert after_warmup[name][2] == 4  # 출전 4쿼터는 세어진다
        assert after_warmup[name][3] == before[name][3]  # 신뢰도도 그대로 (평가 쿼터 0)

    # 3회차: 이제 반영된다. 화이트(하위)가 이겼으니 하위 팀 상승, 상위 팀 하락
    e3 = _event(client, club, "2026-09-20")
    r = client.put(f"{API}/events/{e3}/quarters", json={"quarters": [{"quarter_no": 1, "black_score": 5, "white_score": 20, "lineups": good}]}, headers=m)
    assert r.status_code == 200
    snap = _skills(client, club)
    for name in BOT5:
        assert snap[name][0] > after_warmup[name][0], name
        assert snap[name][3] > after_warmup[name][3]  # 신뢰도 상승
    for name in TOP5:
        assert snap[name][0] < after_warmup[name][0], name
    for name in ("변기훈", "정영삼"):  # 안 뛴 사람은 그대로
        assert snap[name][0] == after_warmup[name][0]
    # 클리핑: 30점 차와 15점 차는 같은 효과
    q2 = client.post(f"{API}/events/{e3}/quarters", json={"quarter_no": 2, "black_score": 0, "white_score": 30, "lineups": good}, headers=m).json()
    with_q2 = _skills(client, club)
    assert client.delete(f"{API}/quarters/{q2['id']}", headers=m).status_code == 204
    assert _skills(client, club) == snap  # 롤백: 정확히 원래 값
    q2b = client.post(f"{API}/events/{e3}/quarters", json={"quarter_no": 2, "black_score": 0, "white_score": 15, "lineups": good}, headers=m).json()
    assert _skills(client, club) == with_q2
    client.delete(f"{API}/quarters/{q2b['id']}", headers=m)

    # 이력: RESIDUAL 로 기록됨 (수치 열람은 매니저 카드로 충분하므로 DB 직접 확인 생략), 플레이어 카드에는 수치 없음
    p = client.get(f"{API}/teams/{club['team_id']}/players", headers=club["members"][1]).json()["items"][0]
    assert "skill_overall" not in p and p["skill_grade"] is None


# 검증: 6.2절 병합 — 게스트로 뛴 쿼터가 병합 후 회원의 기록으로 합산된다
def test_merged_guest_quarters_count_for_member(client, signup, club):
    m = club["manager"]
    eid = _event(client, club, "2026-09-06")
    gid = client.post(f"{API}/events/{eid}/guests", json={"display_name": "최단골", "skill_grade": 3, "playable_positions": ["SF"]}, headers=m).json()["player"]["id"]
    lineups = _lineups(club, TOP5, BOT5[:-1]) + [{"player_id": gid, "side": "WHITE"}]
    assert client.put(f"{API}/events/{eid}/quarters", json={"quarters": [{"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": lineups}]}, headers=m).status_code == 200
    guest_cards = client.get(f"{API}/teams/{club['team_id']}/players?kind=GUEST", headers=m).json()["items"]
    assert next(c for c in guest_cards if c["id"] == gid)["quarters_played"] == 1

    newbie = signup("choi@club.com", name="최단골")
    client.post(f"{API}/teams/join", json={"team_code": client.get(f"{API}/teams/{club['team_id']}", headers=m).json()["team_code"]}, headers=newbie)
    new_pid = client.get(f"{API}/teams/{club['team_id']}", headers=newbie).json()["my_player_id"]
    assert client.post(f"{API}/players/{gid}:merge", json={"into_player_id": new_pid}, headers=m).status_code == 200
    # 병합 즉시 재계산 → 회원 기록에 합산
    member = next(c for c in client.get(f"{API}/teams/{club['team_id']}/players", headers=m).json()["items"] if c["id"] == new_pid)
    assert member["quarters_played"] == 1
    # 병합된 게스트 id 로는 더 이상 라인업에 넣을 수 없다 (회원 이중 계산 방지)
    r = client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 2, "black_score": 1, "white_score": 0, "lineups": lineups}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAYER_NOT_IN_TEAM"
    # 그래도 게스트로 뛴 지난 쿼터는 점수만 고쳐 다시 저장할 수 있다 (기록 화면은 쿼터 전체를 다시 보낸다)
    r = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [{"quarter_no": 1, "black_score": 12, "white_score": 8, "lineups": lineups}]}, headers=m)
    assert r.status_code == 200, r.text
    # 새로 넣는 사람은 여전히 검사한다 — 팀 밖 id 는 422
    swapped = [dict(x, player_id=999999) if x["player_id"] == club["pid"][BOT5[0]] else x for x in lineups]
    r = client.put(f"{API}/events/{eid}/quarters", json={"quarters": [{"quarter_no": 1, "black_score": 12, "white_score": 8, "lineups": swapped}]}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAYER_NOT_IN_TEAM"
    # 되돌리면 회원 기록에서 빠진다
    assert client.post(f"{API}/players/{gid}:unmerge", headers=m).status_code == 200
    member = next(c for c in client.get(f"{API}/teams/{club['team_id']}/players", headers=m).json()["items"] if c["id"] == new_pid)
    assert member["quarters_played"] == 0


# 검증: 확정 배정 밖의 사람도 쿼터에 넣을 수 있다 — 늦게 온 회원, 당일 부른 게스트, 한 경기 뒤 팀을 옮긴 사람
def test_lineup_accepts_late_joiners_and_side_change(client, club, event):
    m = club["manager"]
    # 그날 처음 온 게스트를 활동이 끝난 뒤에 등록해도 참석자로 들어간다 (일정이 DONE 이어도)
    g = client.post(f"{API}/events/{event}/guests", json={"display_name": "당일합류", "force_new": True}, headers=m)
    assert g.status_code == 201, g.text
    guest_id = g.json()["player"]["id"]
    # 1쿼터: 게스트가 블랙으로 뛴다 (참석 응답을 하지 않은 사람 대신)
    q1 = _lineups(club, TOP5[:4], BOT5)
    q1.append({"player_id": guest_id, "side": "BLACK"})
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 1, "black_score": 10, "white_score": 6, "duration_min": 8, "lineups": q1}, headers=m)
    assert r.status_code == 201, r.text
    # 2쿼터: 밸런스를 맞추려고 같은 게스트를 화이트로 옮긴다
    q2 = _lineups(club, TOP5, BOT5[:4])
    q2.append({"player_id": guest_id, "side": "WHITE"})
    r = client.put(f"{API}/events/{event}/quarters", json={"quarters": [
        {"quarter_no": 1, "black_score": 10, "white_score": 6, "duration_min": 8, "lineups": q1},
        {"quarter_no": 2, "black_score": 7, "white_score": 9, "duration_min": 8, "lineups": q2},
    ]}, headers=m)
    assert r.status_code == 200, r.text
    lst = client.get(f"{API}/events/{event}/quarters", headers=m).json()
    sides = {q["quarter_no"]: next(x["side"] for x in q["lineups"] if x["player_id"] == guest_id) for q in lst["items"]}
    assert sides == {1: "BLACK", 2: "WHITE"}
    # 두 사이드로 나뉘어 뛰었어도 출전 쿼터 수는 합쳐서 2
    assert sum(c["quarters"] for c in lst["summary"]["per_player"] if c["player_id"] == guest_id) == 2
    # 같은 쿼터에 양 팀으로 동시에 넣는 것은 여전히 막힌다
    dup = _lineups(club, TOP5[:4], BOT5[:4]) + [{"player_id": guest_id, "side": "BLACK"}, {"player_id": guest_id, "side": "WHITE"}]
    r = client.post(f"{API}/events/{event}/quarters", json={"quarter_no": 3, "black_score": 1, "white_score": 0, "lineups": dup}, headers=m)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"


# 일정 삭제: 참석·배정·투표를 함께 지우고, 그 일정에만 온 게스트도 지운다. 경기 기록이 있으면 막는다
def test_delete_event_removes_records_and_one_off_guests(client, club):
    m, tid = club["manager"], club["team_id"]
    regular = client.post(f"{API}/events/{_event(client, club, '2026-09-06')}/guests", json={"display_name": "단골 게스트", "force_new": True}, headers=m).json()["player"]["id"]

    eid = _event(client, club, "2026-09-13")
    one_off = client.post(f"{API}/events/{eid}/guests", json={"display_name": "한 번 온 게스트", "skill_grade": 3, "force_new": True}, headers=m)
    assert one_off.status_code == 201, one_off.text
    one_off_id = one_off.json()["player"]["id"]
    assert client.post(f"{API}/events/{eid}/guests", json={"display_name": "단골 게스트", "existing_player_id": regular}, headers=m).status_code == 201
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    assert client.post(f"{API}/assignments/candidates/{run['candidates'][0]['id']}:adopt", headers=m).status_code == 200
    # 끝난 일정이라 투표가 열려 있다 — 투표가 있어도 지워져야 한다
    voter = club["members"][1]  # members[0] 은 매니저
    targets = client.get(f"{API}/events/{eid}/post-game-survey", headers=voter).json()["candidates"]
    assert client.post(f"{API}/events/{eid}/post-game-survey", json={"votes": [{"target_player_id": targets[0]["player"]["id"], "vote_type": "PLAY_AGAIN"}]}, headers=voter).status_code == 201

    assert client.delete(f"{API}/events/{eid}", headers=m).status_code == 204
    assert client.get(f"{API}/events/{eid}", headers=m).status_code == 404
    assert client.get(f"{API}/assignments/runs/{run['id']}", headers=m).status_code == 404
    names = [g["display_name"] for g in client.get(f"{API}/teams/{tid}/guests", headers=m).json()["items"]]
    assert "단골 게스트" in names  # 다른 일정에도 온 게스트는 남는다
    assert "한 번 온 게스트" not in names and all(g["id"] != one_off_id for g in client.get(f"{API}/teams/{tid}/guests", headers=m).json()["items"])

    # 경기 기록이 있는 일정은 지울 수 없다
    done = _event(client, club, "2026-09-14")
    q = {"quarter_no": 1, "black_score": 10, "white_score": 8, "lineups": _lineups(club, TOP5, BOT5)}
    assert client.post(f"{API}/events/{done}/quarters", json=q, headers=m).status_code == 201
    r = client.delete(f"{API}/events/{done}", headers=m)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    assert client.get(f"{API}/events/{done}", headers=m).status_code == 200
    # 팀원은 지울 수 없다
    assert client.delete(f"{API}/events/{done}", headers=club["members"][1]).status_code == 403
