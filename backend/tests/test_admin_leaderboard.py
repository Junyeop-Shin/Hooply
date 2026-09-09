"""관리자 API (F12) · 팀 리더보드 — 권한, 검색, 보정 이력, 감사 로그, 참여율/쿼터/잔차 순위."""

from tests.test_ranking_assignment import club  # noqa: F401 — 픽스처 재사용

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
    assert r.status_code == 200 and r.json()["skill_overall"] == "3.5" and r.json()["prior_overall"] == "3.5"
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
