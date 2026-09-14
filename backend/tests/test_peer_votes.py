"""피어 투표 (F9 · F10 · 피어 투표 설계) — 오픈 시점, 후보 명단, 0~2명 검증, 이유 태그, 선호 점수 집계, 독려 메시지, F11.

시나리오: 12명 팀(club 픽스처). 어제 끝난 일정(투표 열림)과 다음 주 일정(아직 안 열림)을 만들고,
참석자들이 투표한 뒤 chemistry_scores 와 "잘 맞는 참여자" 가 투표만으로 만들어지는지 확인한다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from tests.test_ranking_assignment import ROSTER, club  # noqa: F401 — 픽스처 재사용

API = "/api/v1"


def _event(client, club, date, end_time="12:00"):
    m = club["manager"]
    eid = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": date, "start_time": "10:00", "end_time": end_time}, headers=m).json()["id"]
    for h in club["members"]:
        client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h)
    return eid


@pytest.fixture
def past_event(client, club):
    """어제 끝난 일정 → 투표 열림. 매니저 대리 응답으로 참석 처리(마감 무관)."""
    m = club["manager"]
    yesterday = (datetime.now(UTC).astimezone() - timedelta(days=1)).date().isoformat()
    eid = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": yesterday, "start_time": "10:00", "end_time": "12:00"}, headers=m).json()["id"]
    for h in club["members"]:
        client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h)
    return eid


# 검증: 스펙 3.3절 — 종료 시각 전에는 403 SURVEY_NOT_OPEN, 지나면 후보 = 참석자 전원(본인 제외), 비참석자 403
def test_open_timing_and_candidates(client, club, past_event):
    m, p1 = club["manager"], club["members"][1]
    future = _event(client, club, (datetime.now(UTC).astimezone() + timedelta(days=7)).date().isoformat())
    r = client.get(f"{API}/events/{future}/post-game-survey", headers=p1)
    assert r.status_code == 403 and r.json()["code"] == "SURVEY_NOT_OPEN"
    ev = client.get(f"{API}/events/{future}", headers=p1).json()
    assert ev["survey_open"] is False

    r = client.get(f"{API}/events/{past_event}/post-game-survey/candidates", headers=p1)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] and not body["already_submitted"] and len(body["candidates"]) == 11  # 12명 − 본인
    assert all(c["squad_no"] is None for c in body["candidates"])  # 배정 없음 → 팀 배지 없음
    # 불참자는 후보에도 응답자에도 없다
    client.put(f"{API}/events/{past_event}/attendances/{club['pid']['박지수']}", json={"status": "ABSENT"}, headers=m)
    names = [c["player"]["display_name"] for c in client.get(f"{API}/events/{past_event}/post-game-survey", headers=p1).json()["candidates"]]
    assert "박지수" not in names
    r = client.get(f"{API}/events/{past_event}/post-game-survey", headers=club["members"][11])
    assert r.status_code == 403 and r.json()["code"] == "NOT_ATTENDEE"


# 검증: 같은 팀 최대 2 + 상대 팀 최대 2 (배정 없으면 합계 4), 본인 400, BEST_PERFORMER 400, 빈 제출 가능, 재제출 409
def test_submit_rules(client, club, past_event):
    pid = club["pid"]
    p1, p2 = club["members"][1], club["members"][2]
    me = pid["이정현"]
    post = lambda h, votes: client.post(f"{API}/events/{past_event}/post-game-survey", json={"votes": votes}, headers=h)
    r = post(p1, [{"target_player_id": me, "vote_type": "PLAY_AGAIN"}])
    assert r.status_code == 400 and r.json()["code"] == "SELF_VOTE_NOT_ALLOWED"
    r = post(p1, [{"target_player_id": pid[n], "vote_type": "PLAY_AGAIN"} for n in ("최준용", "함지훈", "이규섭", "양희승", "변기훈")])
    assert r.status_code == 400  # 배정 없는 회차: 팀 구분이 없어 합계 4명 (스키마 max_length=4 에서 먼저 걸린다)
    r = post(p1, [{"target_player_id": pid["최준용"], "vote_type": "BEST_PERFORMER"}])
    assert r.status_code == 400  # '잘한 사람' 투표는 받지 않는다
    r = post(p1, [{"target_player_id": 999999, "vote_type": "PLAY_AGAIN"}])
    assert r.status_code == 400
    r = post(p1, [
        {"target_player_id": pid["최준용"], "vote_type": "PLAY_AGAIN", "reason_tag": "PASS"},
        {"target_player_id": pid["함지훈"], "vote_type": "PLAY_AGAIN"},
    ])
    assert r.status_code == 201, r.text
    assert r.json()["already_submitted"] and len(r.json()["my_votes"]) == 2
    assert any(v["reason_tag"] == "PASS" for v in r.json()["my_votes"])
    assert post(p1, []).status_code == 409
    # 빈 제출도 응답으로 친다
    assert post(p2, []).status_code == 201
    ev = client.get(f"{API}/events/{past_event}", headers=p1).json()
    assert ev["my_survey_submitted"] is True and ev["survey_responded"] == 2 and ev["survey_total"] == 12


# 검증: 확정 배정이 있으면 같은 팀 / 상대 팀 각각 최대 2명
def test_submit_per_side_limit(client, club, past_event):
    m = club["manager"]
    run = client.post(f"{API}/events/{past_event}/assignments", json={"team_count": 2}, headers=m).json()
    client.post(f"{API}/assignments/candidates/{run['candidates'][0]['id']}:adopt", headers=m)
    p1 = club["members"][1]
    body = client.get(f"{API}/events/{past_event}/post-game-survey", headers=p1).json()
    same = [c["player"]["id"] for c in body["candidates"] if c["is_same_team"]]
    opp = [c["player"]["id"] for c in body["candidates"] if c["is_same_team"] is False]
    assert len(same) >= 3 and len(opp) >= 3
    post = lambda votes: client.post(f"{API}/events/{past_event}/post-game-survey", json={"votes": votes}, headers=p1)
    r = post([{"target_player_id": x, "vote_type": "PLAY_AGAIN"} for x in same[:3]])
    assert r.status_code == 400 and "같은 팀" in r.json()["message"]
    r = post([{"target_player_id": x, "vote_type": "PLAY_AGAIN"} for x in same[:2] + opp[:2]])
    assert r.status_code == 201, r.text
    assert len(r.json()["my_votes"]) == 4


# 검증: 스펙 4.1절 — pref_score = 지목/함께 참석 (최근 가중), 상호 지목 mutual, BEST 는 pref 에 영향 없음, 배정 후보 배지
def test_chemistry_aggregation_and_compatible(client, club, past_event):
    pid, m = club["pid"], club["manager"]
    h = {n: club["members"][i] for i, (n, *_) in enumerate(ROSTER)}
    post = lambda who, votes: client.post(f"{API}/events/{past_event}/post-game-survey", json={"votes": votes}, headers=h[who])
    # 최준용 ↔ 이정현 상호 지목, 함지훈 → 최준용 단방향
    assert post("최준용", [{"target_player_id": pid["이정현"], "vote_type": "PLAY_AGAIN", "reason_tag": "TEMPO"}]).status_code == 201
    assert post("이정현", [{"target_player_id": pid["최준용"], "vote_type": "PLAY_AGAIN"}]).status_code == 201
    assert post("함지훈", [{"target_player_id": pid["최준용"], "vote_type": "PLAY_AGAIN"}]).status_code == 201

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import ChemistryScore

    with SessionLocal() as db:
        rows = {(c.player_a_id, c.player_b_id): c for c in db.scalars(select(ChemistryScore)).all()}
        a, b = sorted((pid["최준용"], pid["이정현"]))
        assert rows[(a, b)].pref_mutual is True and float(rows[(a, b)].pref_score) == 1.0 and rows[(a, b)].together_events == 1
        a2, b2 = sorted((pid["함지훈"], pid["최준용"]))
        assert rows[(a2, b2)].pref_mutual is False and float(rows[(a2, b2)].pref_score) == 0.5  # 한 방향만 1.0 → 평균 0.5

    # F11 API: 최준용의 잘 맞는 참여자 — 이정현(상호) 먼저, 함지훈(단방향)
    r = client.get(f"{API}/players/{pid['최준용']}/compatible", headers=h["최준용"])
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["player"]["display_name"] == "이정현" and items[0]["mutual_play_again"] is True
    assert {i["player"]["display_name"] for i in items} == {"이정현", "함지훈"}
    # 남의 목록은 매니저만
    assert client.get(f"{API}/players/{pid['최준용']}/compatible", headers=h["이정현"]).status_code == 403
    assert client.get(f"{API}/players/{pid['최준용']}/compatible", headers=m).status_code == 200

    # 두 번째 회차: 함께 참석했지만 지목 없음 → 분모 2, 최근 회차 미지목 → 0.9^1/2 = 0.45 (양방향 평균 0.45)
    yesterday2 = (datetime.now(UTC).astimezone() - timedelta(days=8)).date().isoformat()
    _event(client, club, yesterday2)  # 지난주 (더 오래된 회차) → 최신순에서 k=1 이 과거 투표
    # 재계산은 제출 시에만 도니 한 번 더 제출로 트리거
    assert post("양희승", []).status_code == 201
    with SessionLocal() as db:
        c = db.scalar(select(ChemistryScore).where(ChemistryScore.player_a_id == a, ChemistryScore.player_b_id == b))
        assert c.together_events == 2 and float(c.pref_score) == 0.5  # 최신(어제) 회차 지목 1.0 / 2 = 0.5


# 검증: 스펙 3.3절 — 독려 메시지는 매니저만, 링크와 응답 현황 포함. 자동 발송 없음
def test_share_message(client, club, past_event):
    m, p1 = club["manager"], club["members"][1]
    assert client.get(f"{API}/events/{past_event}/post-game-survey/share-message", headers=p1).status_code == 403
    r = client.get(f"{API}/events/{past_event}/post-game-survey/share-message", headers=m)
    assert r.status_code == 200
    body = r.json()
    assert f"/events/{past_event}/vote" in body["link"] and body["link"] in body["text"] and "투표" in body["text"]
    assert body["responded"] == 0 and body["total"] == 12 and body["open"] is True


# 검증: FR-28 · FR-31 — 선수 통계. 본인은 쿼터 기록·마진만, 매니저는 실력 수치·정렬 순위·지목 수까지
def test_player_stats(client, club, past_event):
    m, pid = club["manager"], club["pid"]
    ids = list(pid.values())
    me_id = pid["이정현"]
    others = [x for x in ids if x != me_id]
    lineups = [{"player_id": x, "side": "BLACK"} for x in [me_id, *others[:4]]] + [{"player_id": x, "side": "WHITE"} for x in others[4:9]]  # 이정현은 블랙
    r = client.put(f"{API}/events/{past_event}/quarters", json={"quarters": [
        {"quarter_no": 1, "black_score": 12, "white_score": 9, "duration_min": 6, "lineups": lineups},
        {"quarter_no": 2, "black_score": 8, "white_score": 10, "lineups": lineups},
    ]}, headers=m)
    assert r.status_code == 200, r.text
    client.post(f"{API}/teams/{club['team_id']}/rankings", json={"player_ids": ids}, headers=m)
    me = club["members"][1]  # 이정현 (ROSTER 두 번째) → 블랙
    r = client.get(f"{API}/players/{pid['이정현']}/stats", headers=me)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["quarters_played"] == 2 and s["events_attended"] == 1
    assert s["skill_overall"] is None and s["history"] == []  # 본인에게는 수치 없음
    assert s["skill_grade"] is not None  # 등급은 본인에게만 보인다 (9.2절)
    assert [q["quarter_no"] for q in s["recent_quarters"]] == [2, 1]
    assert s["recent_quarters"][1]["my_score"] == 12 and float(s["recent_quarters"][1]["normalized_margin"]) == 5.0
    assert s["margin_trend"][0]["wins"] == 1 and s["margin_trend"][0]["losses"] == 1
    # 남의 통계는 매니저만
    assert client.get(f"{API}/players/{pid['최준용']}/stats", headers=me).status_code == 403
    r = client.get(f"{API}/players/{pid['이정현']}/stats", headers=m)
    assert r.status_code == 200
    s = r.json()
    assert s["skill_grade"] is not None and s["prior_overall"] is not None and s["manager_rank"]["rank_no"] == ids.index(pid["이정현"]) + 1
    assert s["play_again_received"] == 0
