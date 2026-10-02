"""관리자 API (F12) · 팀 리더보드 — 권한, 검색, 보정 이력, 감사 로그, 참여율/쿼터/기여 점수 순위."""

from tests.test_ranking_assignment import ROSTER, club  # noqa: F401 — 픽스처 재사용

API = "/api/v1"


def _make_admin(client, signup):
    headers = signup()  # signup 팩토리 또는 호환 callable
    uid = client.get(f"{API}/me", headers=headers).json()["id"]
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models import User
    from app.models.enums import GlobalRole

    with SessionLocal() as db:
        db.execute(update(User).where(User.id == uid).values(global_role=GlobalRole.ADMIN))
        db.commit()
    return headers


# 검증: 3.3절 — 관리자 API 는 ADMIN 만. 사용자 검색 · 원시 데이터 · 보정(이력+감사 로그)
def test_admin_endpoints(client, signup, club):
    admin = _make_admin(client, signup)
    player = client.get(f"{API}/me", headers=club["members"][1])
    assert client.get(f"{API}/admin/users", headers=club["manager"]).status_code == 403
    r = client.get(f"{API}/admin/users?q=이정현", headers=admin)
    assert r.status_code == 200 and r.json()["meta"]["total"] == 1 and r.json()["items"][0]["name"] == "이정현"
    pid = club["pid"]["이정현"]
    raw = client.get(f"{API}/admin/players/{pid}/raw", headers=admin).json()
    assert raw["player"]["id"] == pid and raw["profile"] is not None and len(raw["survey_answers"]) > 0
    before = raw["profile"]["skill_overall"] or raw["profile"]["prior_overall"]
    r = client.patch(f"{API}/admin/players/{pid}/rating", json={"skill_overall": 3.5, "reason": "테스트 보정"}, headers=admin)
    # 사전값은 그대로 두고 보정은 admin_adjust 로 따로 둔다 (설문 · 정렬 재계산에 지워지지 않게)
    assert r.status_code == 200 and r.json()["skill_overall"] == "3.5" and r.json()["prior_overall"] == raw["profile"]["prior_overall"]
    raw2 = client.get(f"{API}/admin/players/{pid}/raw", headers=admin).json()
    assert raw2["rating_history"][-1]["source"] == "ADMIN_ADJUST" and raw2["rating_history"][-1]["reason"] == "테스트 보정"
    logs = client.get(f"{API}/admin/audit-logs", headers=admin).json()
    assert logs["meta"]["total"] == 1 and logs["items"][0]["action"] == "ADMIN_RATING_ADJUST" and logs["items"][0]["before"]["skill_overall"] in (before, None)
    assert player.status_code == 200


# 검증: 리더보드 — 참여율은 전원, 잔차는 매니저만. 참석 기록으로 순위가 바뀐다
def test_leaderboard(client, club):
    m, p1, tid, pid = club["manager"], club["members"][1], club["team_id"], club["pid"]
    eid = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-09-01", "start_time": "10:00", "end_time": "12:00"}, headers=m).json()["id"]
    for n in ("최준용", "이정현", "함지훈"):
        client.put(f"{API}/events/{eid}/attendances/{pid[n]}", json={"status": "ATTEND"}, headers=m)
    r = client.get(f"{API}/teams/{tid}/stats/leaderboard?metric=attendance", headers=p1)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["rank"] == 1 and float(items[0]["value"]) == 1.0 and items[0]["player"]["skill_grade"] is None
    assert {i["player"]["display_name"] for i in items[:3]} == {"최준용", "이정현", "함지훈"}
    assert float(items[-1]["value"]) == 0.0
    assert client.get(f"{API}/teams/{tid}/stats/leaderboard?metric=residual", headers=p1).status_code == 403
    r = client.get(f"{API}/teams/{tid}/stats/leaderboard?metric=residual", headers=m)
    assert r.status_code == 200 and r.json()["items"][0]["player"]["skill_grade"] is not None
    assert client.get(f"{API}/teams/{tid}/stats/leaderboard?metric=quarters&period=2026-09", headers=p1).status_code == 200
    assert client.get(f"{API}/teams/{tid}/stats/leaderboard?period=abc", headers=p1).status_code == 400


# 검증: 팀 생성 승인 — 승인 전에는 5명이 모여도 PENDING·일정 등록 불가, 승인하면 ACTIVE, 거절하면 다시 PENDING
def test_team_approval_flow(client, signup):
    from app.core.config import get_settings

    get_settings().team_approval_required = True
    try:
        owner = signup("owner@x.com", name="팀장")
        team = client.post(f"{API}/teams", json={"name": "승인팀"}, headers=owner).json()
        for i in range(4):
            client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=signup(f"u{i}@x.com", name=f"회원{i}"))
        d = client.get(f"{API}/teams/{team['id']}", headers=owner).json()
        assert d["approval_status"] == "PENDING" and d["status"] == "PENDING" and d["member_count"] == 5
        r = client.post(f"{API}/teams/{team['id']}/events", json={"event_date": "2026-09-20"}, headers=owner)
        assert r.status_code == 422 and "승인" in r.json()["message"]
        admin = _make_admin(client, lambda **kw: signup("adm@x.com", name="관리자"))
        assert client.post(f"{API}/admin/teams/{team['id']}:approve", headers=owner).status_code == 403
        pending = client.get(f"{API}/admin/teams?approval=PENDING", headers=admin).json()["items"]
        assert [t["id"] for t in pending] == [team["id"]]
        r = client.post(f"{API}/admin/teams/{team['id']}:approve", headers=admin)
        assert r.status_code == 200 and r.json()["approval_status"] == "APPROVED" and r.json()["status"] == "ACTIVE"
        assert client.post(f"{API}/teams/{team['id']}/events", json={"event_date": "2026-09-20"}, headers=owner).status_code == 201
        r = client.post(f"{API}/admin/teams/{team['id']}:reject", headers=admin)
        assert r.json()["approval_status"] == "REJECTED" and r.json()["status"] == "PENDING"
        assert client.get(f"{API}/admin/audit-logs", headers=admin).json()["items"][0]["action"] == "TEAM_REJECT"
    finally:
        get_settings().team_approval_required = False


# 검증: 기여 점수는 기간마다 달라야 한다 — 프로필 누적 총합을 그대로 쓰면 어느 달을 골라도 같은 값이 나온다
def test_leaderboard_residual_is_scoped_to_period(client, club):
    m, tid, pid = club["manager"], club["team_id"], club["pid"]
    names = [n for n, *_ in ROSTER][:10]
    lineups = (
        [{"player_id": pid[n], "side": "BLACK"} for n in names[:5]]
        + [{"player_id": pid[n], "side": "WHITE"} for n in names[5:]]
    )

    def record(day: str, black: int, white: int) -> None:
        eid = client.post(f"{API}/teams/{tid}/events", json={"event_date": day, "start_time": "10:00", "end_time": "12:00"}, headers=m).json()["id"]
        for n in names:
            client.put(f"{API}/events/{eid}/attendances/{pid[n]}", json={"status": "ATTEND"}, headers=m)
        r = client.post(f"{API}/events/{eid}/quarters", json={"quarter_no": 1, "black_score": black, "white_score": white, "duration_min": 8, "lineups": lineups}, headers=m)
        assert r.status_code == 201, r.text

    # 앞의 두 일정은 지표에 넣지 않는 구간(13.2절 1항)이라 기여도가 0 이다. 그 뒤 두 달에만 값이 생긴다
    record("2026-06-07", 10, 8)
    record("2026-06-14", 10, 8)
    record("2026-07-05", 20, 4)
    record("2026-08-02", 4, 20)

    def scores(period: str | None) -> dict[str, float]:
        url = f"{API}/teams/{tid}/stats/leaderboard?metric=residual" + (f"&period={period}" if period else "")
        r = client.get(url, headers=m)
        assert r.status_code == 200, r.text
        return {i["player"]["display_name"]: float(i["value"]) for i in r.json()["items"]}

    total, jun, jul, aug = scores(None), scores("2026-06"), scores("2026-07"), scores("2026-08")
    top = names[0]  # 블랙에서 뛴 사람
    assert jun[top] == 0.0  # 첫 두 일정은 지표 미반영
    assert jul[top] > 0 and aug[top] < 0  # 7월엔 크게 이기고 8월엔 크게 졌다
    assert jul[top] != total[top] and aug[top] != total[top]  # 기간마다 값이 다르다
    assert round(jun[top] + jul[top] + aug[top], 1) == round(total[top], 1)  # 달을 합치면 전체가 된다
    # 기록이 없는 달은 0 (요청 자체는 유효)
    assert scores("2026-05")[top] == 0.0

    # 그 달에 안 뛴 사람은 못 뛴 게 아니라 기록이 없는 것 — 0 으로 쳐서 중간에 끼지 않고 맨 아래로 간다
    r = client.get(f"{API}/teams/{tid}/stats/leaderboard?metric=residual&period=2026-08", headers=m)
    items = r.json()["items"]
    played = [i for i in items if i["detail"] != "출전 없음"]
    assert played and all(i["rank"] < min(x["rank"] for x in items if x["detail"] == "출전 없음") for i in played)
    assert any(float(i["value"]) < 0 for i in played)  # 못한 사람도 안 나온 사람보다 위


# 검증: 월 선택 목록에는 기록이 있는 달만, 최신순으로 들어간다
def test_leaderboard_periods_lists_only_months_with_records(client, club):
    m, tid = club["manager"], club["team_id"]
    for day in ("2026-06-07", "2026-08-02", "2026-08-30"):
        client.post(f"{API}/teams/{tid}/events", json={"event_date": day}, headers=m)
    canceled = client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-05-03"}, headers=m).json()["id"]
    client.delete(f"{API}/events/{canceled}", headers=m)
    r = client.get(f"{API}/teams/{tid}/stats/periods", headers=club["members"][1])
    assert r.status_code == 200, r.text
    assert r.json()["items"] == ["2026-08", "2026-06"]  # 최신순, 같은 달은 한 번, 취소된 일정의 5월은 없다
