"""기록 탭 — 월간 코트 마진 랭킹(출전 비율 기준)과 배지(행동 성취)."""

from tests.test_ranking_assignment import ROSTER, club  # noqa: F401 — 12명 팀 픽스처 재사용

API = "/api/v1"


def _month_of_games(client, club):
    """9월에 세 번 모여 4 + 4 + 2 = 10쿼터. 11번째 사람(ROSTER[10])은 마지막 날 2쿼터만 뛰고 크게 이긴다."""
    m, tid, pid = club["manager"], club["team_id"], club["pid"]
    names = [n for n, *_ in ROSTER]
    base = [{"player_id": pid[n], "side": "BLACK"} for n in names[:5]] + [{"player_id": pid[n], "side": "WHITE"} for n in names[5:10]]
    late = [{"player_id": pid[names[10]], "side": "BLACK"}] + base[1:]  # names[0] 대신 names[10]
    plan = [("2026-09-06", 4, base, (12, 8)), ("2026-09-13", 4, base, (8, 12)), ("2026-09-20", 2, late, (30, 2))]
    for day, n_q, lineups, (b, w) in plan:
        eid = client.post(f"{API}/teams/{tid}/events", json={"event_date": day, "start_time": "10:00", "end_time": "12:00"}, headers=m).json()["id"]
        for h in club["members"]:  # 전원 참석 응답 (본인이 직접)
            assert client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h).status_code == 200
        for q in range(1, n_q + 1):
            r = client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": q, "black_score": b, "white_score": w, "duration_min": 10, "lineups": lineups}, headers=m)
            assert r.status_code == 201, r.text
    return names


def test_monthly_margin_ranks_by_average_with_share_threshold(client, club):
    m, tid = club["manager"], club["team_id"]
    names = _month_of_games(client, club)
    r = client.get(f"{API}/teams/{tid}/stats/monthly-margin?period=2026-09", headers=club["members"][3])  # 플레이어도 볼 수 있다
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["total_quarters"] == 10 and v["threshold_quarters"] == 3 and v["min_share"] == 0.3
    by = {e["player"]["display_name"]: e for e in v["items"]}
    # 2쿼터만 뛴 사람은 평균이 제일 높아도(+28) 순위가 없고 맨 아래
    late = by[names[10]]
    assert late["quarters"] == 2 and late["eligible"] is False and late["rank"] is None and float(late["avg_margin"]) == 28.0
    assert v["items"][-1]["player"]["display_name"] == names[10]
    # 블랙 주전(names[1]): 4쿼터 +4, 4쿼터 −4, 2쿼터 +28 → 평균 (16 − 16 + 56)/10 = 5.6, 6승 4패
    top = by[names[1]]
    assert top["quarters"] == 10 and top["eligible"] and float(top["avg_margin"]) == 5.6 and top["wins"] == 6
    # 기준 충족자는 평균 내림차순, 순위는 1부터 이어진다
    elig = [e for e in v["items"] if e["eligible"]]
    assert [e["rank"] for e in elig] == list(range(1, len(elig) + 1))
    assert [float(e["avg_margin"]) for e in elig] == sorted((float(e["avg_margin"]) for e in elig), reverse=True)
    # 그 달 출전이 없는 사람(names[11])은 목록에 없다
    assert names[11] not in by
    # 기록 없는 달은 빈 목록, 형식이 틀리면 400
    assert client.get(f"{API}/teams/{tid}/stats/monthly-margin?period=2026-08", headers=m).json()["items"] == []
    assert client.get(f"{API}/teams/{tid}/stats/monthly-margin?period=2026-9", headers=m).status_code == 400


def test_badges_follow_behaviour_and_never_revoke(client, club):
    m = club["manager"]
    names = _month_of_games(client, club)
    items = client.get(f"{API}/me/badges", headers=m).json()["items"]
    by = {b["code"]: b for b in items}
    assert len(items) == 19 and all(b["group"] in ("START", "ACTIVITY", "RELATION") for b in items)
    earned = {c for c, b in by.items() if b["earned_at"]}
    # 시작 배지 4개 + 첫 출전 + 3회 연속 참석. 매니저(names[0])는 8쿼터 뛰었고 세 번 다 나왔다
    assert {"JOIN_TEAM", "SURVEY_DONE", "SELF_RANK_DONE", "FIRST_RSVP", "FIRST_QUARTER", "STREAK_3"} <= earned
    assert by["QUARTERS_10"]["earned_at"] is None and by["QUARTERS_10"]["progress"] == 8
    assert by["ATTEND_5"]["earned_at"] is None and by["ATTEND_5"]["progress"] == 3
    assert by["FIRST_VOTE"]["earned_at"] is None and by["FIRST_VOTE"]["progress"] == 0
    # 다시 불러도 같은 결과, 획득 시각은 그대로
    again = {b["code"]: b for b in client.get(f"{API}/me/badges", headers=m).json()["items"]}
    assert again["FIRST_QUARTER"]["earned_at"] == by["FIRST_QUARTER"]["earned_at"]
    # 출전이 없는 사람(names[11])은 활동 배지가 없다
    none = {b["code"]: b for b in client.get(f"{API}/me/badges", headers=club["members"][11]).json()["items"]}
    assert none["FIRST_QUARTER"]["earned_at"] is None and none["FIRST_RSVP"]["earned_at"] is not None
    _ = names
