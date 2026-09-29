"""자주 열리는 화면의 SQL 문 수 상한 — 사람 수에 비례해 늘어나는 조회(N+1)가 다시 생기면 여기서 잡힌다.

12명 팀(club 픽스처)으로 각 엔드포인트를 한 번 부르고, 실행된 SQL 문 수가 상한 이하인지 본다.
상한은 지금 값에 여유를 조금 둔 것이라, 정당한 이유로 쿼리가 늘면 숫자를 올리되 "사람 수와 무관한가" 를 먼저 확인한다.
"""

import pytest
from sqlalchemy import event as sa_event

from app.db.session import engine
from tests.test_ranking_assignment import _event_with_attendance, club  # noqa: F401 — 픽스처 재사용

API = "/api/v1"


@pytest.fixture
def sql_count():
    """`with sql_count() as n: ...` 뒤 `n[0]` 이 그 블록에서 실행된 SQL 문 수."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        box = [0]

        def _tick(conn, cursor, statement, parameters, context, executemany):
            box[0] += 1

        sa_event.listen(engine, "before_cursor_execute", _tick)
        try:
            yield box
        finally:
            sa_event.remove(engine, "before_cursor_execute", _tick)

    return _ctx


def test_hot_endpoints_stay_within_query_budget(client, club, sql_count, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "llm_api_key", "")  # AI 전술 설명은 키 없이 — 규칙 재료를 모으는 쿼리만 센다
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    m, tid = club["manager"], club["team_id"]
    eid, _ = _event_with_attendance(client, club)
    assert client.post(f"{API}/teams/{tid}/rankings", json={"player_ids": list(club["pid"].values())}, headers=m).status_code == 201
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    assert client.post(f"{API}/assignments/candidates/{run['candidates'][0]['id']}:adopt", headers=m).status_code == 200

    budget = {
        ("GET", "/me/profile"): 12,
        ("GET", f"/teams/{tid}/rankings/latest"): 10,
        ("GET", f"/teams/{tid}/players"): 10,
        ("GET", f"/events/{eid}"): 7,  # 일정 하나: 집계 5개 + 내 상태를 UNION ALL 로 한 번에
        ("GET", f"/events/{eid}/attendances"): 10,  # 이 회차에 없는 지난 게스트는 읽지 않는다
        ("GET", f"/players/{next(iter(club['pid'].values()))}/stats"): 13,  # 세부 능력 팀 내 위치 계산 1개 포함
        ("GET", f"/events/{eid}/assignment/adopted"): 10,  # 선수 프로필 · 계정은 조인으로 (PLAYER_LOAD)
        ("GET", f"/assignments/runs/{run['id']}"): 11,
        # 실행·저장 포함 (2026-09 30 → 18). 후보안을 한 번에 저장하고, 지난 실행은 DB 연쇄 삭제로(자식 행을 읽지 않음),
        # 응답은 방금 읽은 명단을 다시 쓴다
        ("POST", f"/events/{eid}/assignments"): 21,
        # 전술 화면은 추천 · AI 설명을 팀마다 부른다 — 설문 재료는 그날 명단만 읽는다 (20 → 15)
        ("GET", f"/events/{eid}/tactics/recommend"): 17,
        ("GET", f"/events/{eid}/tactics/preset:horns"): 17,
        ("POST", f"/events/{eid}/tactics/ai-recommend?squad_no=1"): 17,
        ("GET", f"/events/{eid}/assignment/suggestions"): 10,  # 대상 참석 상태 · 선수를 한 번에
        ("GET", f"/events/{eid}/guests/presets"): 6,  # 이어 쓸 게스트를 한 번에
        ("GET", "/me/guest-claims"): 7,
        ("GET", "/me/badges"): 16,
    }
    over = {}
    for (method, path), limit in budget.items():
        with sql_count() as n:
            r = client.request(method, API + path, headers=m, json={"team_count": 2} if path.endswith("/assignments") else None)
        assert r.status_code in (200, 201), (path, r.text)
        if n[0] > limit:
            over[f"{method} {path}"] = (n[0], limit)
    assert not over, f"쿼리 수가 상한을 넘었어요 (실행 수, 상한): {over}"
