"""설문 다시 하기 (docs/09 3-10) — 강제하지 않고 원하는 사람만. 30일에 한 번, 지난 답을 불러와 고친다.

- 지난 답을 그대로 돌려준다(다시 할 때 채워 넣기) · 다시 할 수 있는 날짜를 프로필이 알려 준다
- 30일 안에는 409, 지나면 답을 덮어쓰고 포지션 · 팀 사전값을 다시 계산한다
- 한 번도 안 한 사람은 다시 하기가 아니라 처음 설문으로
"""

from datetime import UTC, datetime, timedelta

from tests.test_survey_guest_event import (  # noqa: F401 — 픽스처 재사용
    _answers,
    _player_id,
    _submit,
    _template,
    team,
)

API = "/api/v1"
URL = f"{API}/surveys/onboarding/responses"


def _top_answers(tpl):
    """모든 문항에서 가장 높은 쪽 — 서열 문항은 마지막 선택지, 공격 옵션은 전부, 포지션은 C → PF, 1번 · 5번 가능."""
    out = []
    for q in tpl["questions"]:
        opts = q["options"]
        by_code = {o["code"]: o["id"] for o in opts}
        if q["code"] == "D1":
            ids = [by_code["C"], by_code["PF"]]
        elif q["answer_type"] == "MULTI_CHIP":
            ids = [o["id"] for o in opts]
        elif q["answer_type"] == "TRIO":
            ids = [opts[0]["id"]]
        else:
            ids = [opts[-1]["id"]]
        out.append({"question_id": q["id"], "selected_option_ids": ids})
    return out


def _later(monkeypatch, days):
    from app.services import survey_service

    at = datetime.now(UTC) + timedelta(days=days)
    monkeypatch.setattr(survey_service, "_now", lambda: at)
    return at


# 검증: 지난 답 조회 → 30일 안에는 409 → 지나면 덮어쓰고 포지션이 바뀐다. 답은 문항당 한 줄 그대로
def test_retake_after_30_days_replaces_answers(client, signup, monkeypatch):
    h = signup("re@t.com", name="다시")
    tpl = _template(client)
    first = _submit(client, h, tpl)
    assert first["playable_positions"] == ["SF", "SG"]
    submitted = datetime.fromisoformat(first["survey_submitted_at"])
    assert datetime.fromisoformat(first["survey_retake_at"]) == submitted + timedelta(days=30)

    mine = client.get(f"{URL}/me", headers=h)
    assert mine.status_code == 200, mine.text
    sent = {a["question_id"]: a["selected_option_ids"] for a in _answers(tpl)}
    assert {a["question_id"]: a["selected_option_ids"] for a in mine.json()["answers"]} == sent  # D1 선호 순서까지 그대로
    assert mine.json()["template_id"] == tpl["template_id"] and mine.json()["retake_at"] == first["survey_retake_at"]

    body = {"template_id": tpl["template_id"], "answers": _top_answers(tpl)}
    r = client.put(URL, json=body, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_SUBMITTED"
    assert "다시 할 수 있어요" in r.json()["message"]
    # 처음 설문 경로(POST)도 여전히 409 — 없는 "매니저 보정" 을 가리키지 않는다
    again = client.post(URL, json={"answers": _answers(tpl)}, headers=h)
    assert again.status_code == 409 and "보정" not in again.json()["message"]

    at = _later(monkeypatch, 31)
    # 형식이 틀리면 400 이고 지난 답은 그대로 남는다
    assert client.put(URL, json={"answers": _top_answers(tpl)[:-1]}, headers=h).status_code == 400
    assert {a["question_id"]: a["selected_option_ids"] for a in client.get(f"{URL}/me", headers=h).json()["answers"]} == sent
    r = client.put(URL, json=body, headers=h)
    assert r.status_code == 200, r.text
    prof = r.json()
    assert prof["onboarding_completed"] is True
    assert prof["playable_positions"][:2] == ["C", "PF"] and prof["primary_position"] == "C"
    assert abs((datetime.fromisoformat(prof["survey_submitted_at"]) - at).total_seconds()) < 5
    now = client.get(f"{URL}/me", headers=h).json()
    assert len(now["answers"]) == len(tpl["questions"])
    assert {a["question_id"]: a["selected_option_ids"] for a in now["answers"]} == {a["question_id"]: a["selected_option_ids"] for a in _top_answers(tpl)}
    # 방금 다시 했으면 또 30일을 기다린다
    assert client.put(URL, json=body, headers=h).status_code == 409


# 검증: 한 번도 설문을 안 한 사람은 다시 하기 · 지난 답 조회가 404 (처음 설문은 POST)
def test_retake_needs_a_first_response(client, signup):
    h = signup("none@t.com", name="아직")
    tpl = _template(client)
    assert client.get(f"{URL}/me", headers=h).status_code == 404
    assert client.put(URL, json={"answers": _answers(tpl)}, headers=h).status_code == 404
    assert client.get(f"{API}/me/profile", headers=h).json()["survey_retake_at"] is None


# 검증: 다시 하면 소속 팀의 사전값을 다시 계산한다 — 모두 같은 답(사전값 0)에서 한 사람만 높게 답하면 그 사람이 올라간다
def test_retake_recomputes_team_prior(client, team, monkeypatch):
    m, tid = team["manager"], team["team_id"]
    tpl = _template(client)
    for h in [m, *team["members"]]:
        _submit(client, h, tpl)
    me = team["members"][0]
    pid = _player_id(client, me, tid)

    def prior():
        cards = client.get(f"{API}/teams/{tid}/players", headers=m).json()["items"]
        return float(next(c for c in cards if c["id"] == pid)["prior_overall"])

    assert prior() == 0.0
    _later(monkeypatch, 31)
    r = client.put(URL, json={"answers": _top_answers(tpl)}, headers=me)
    assert r.status_code == 200, r.text
    assert prior() > 0.5
    hist = client.get(f"{API}/players/{pid}/stats", headers=m).json()["history"]
    assert any(x["source"] == "SURVEY" and float(x["after_value"]) > 0.5 for x in hist)  # 이력에도 남는다
