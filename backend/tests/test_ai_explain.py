"""AI 배정 설명 체인 A(매니저) · B(팀원) (docs/07 FR-51, T10 · T11 · T13).

모델 자리에 LangChain Runnable 을 끼워 고정 결과를 돌려준다 (CI 에 키가 없다). 보낸 입력에 실명·실력 값이 없는지도 확인한다.
"""

import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.core.config import get_settings
from app.llm import model as llm_model
from app.llm.prompts import ExplainA, PlayerMessage, TeamMessagesB
from tests.test_ranking_assignment import ROSTER, _event_with_attendance, club  # noqa: F401

API = "/api/v1"
NAMES = [r[0] for r in ROSTER]


@pytest.fixture
def fake(monkeypatch):
    """체인에 따라 고정 결과를 돌려준다. sent 에 보낸 human 메시지를 모은다."""
    state = {"calls": {"A": 0, "B": 0}, "sent": [], "b_text": "{p}는 {pos} 자리예요. 팀에 가드 {g}명이 있어 든든해요."}

    def structured(schema):
        def respond(messages):
            human = dict(messages)["human"]
            state["sent"].append(human)
            data = json.loads(human)
            if schema is ExplainA:
                state["calls"]["A"] += 1
                spread = data["balance"]["skill_spread"]
                return ExplainA(
                    summary="A와 B의 실력이 비슷해요.",
                    reasons=[f"평균 실력 차가 {spread}점이에요.", f"A는 {data['teams'][0]['size']}명이에요.", "P1이 볼을 운반해요."],
                    watch_point="게스트 실력은 평균으로 가정했어요.",
                )
            state["calls"]["B"] += 1
            guards = next((t for t in data["team_traits"] if t.startswith("가드")), "가드 0명").split()[1].rstrip("명")
            return TeamMessagesB(messages=[
                PlayerMessage(player=p["id"], message=state["b_text"].format(p=p["id"], pos=p["position"] or "자유", g=guards))
                for p in data["players"]
            ])
        return RunnableLambda(respond)

    monkeypatch.setattr(llm_model, "structured", structured)
    return state


def _adopt(client, club):
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club)
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    cand = run["candidates"][0]
    assert client.post(f"{API}/assignments/candidates/{cand['id']}:adopt", headers=m).status_code == 200
    return eid, run, cand


def test_no_key_everything_falls_back(client, club, monkeypatch):
    """T10: 키가 없으면 A·B 모두 기존 규칙 문장, 오류 없음."""
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    eid, _, cand = _adopt(client, club)
    r = client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=club["manager"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fallback"] is True and body["text"] == cand["explanation"] and body["reasons"] == []
    r = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][3])
    assert r.status_code == 200 and r.json()["fallback"] is True and r.json()["message"]


def test_manager_explanation_uses_aliases_and_restores(client, club, fake):
    m = club["manager"]
    _, run, cand = _adopt(client, club)
    r = client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fallback"] is False and body["cached"] is False and body["text"] is None
    assert body["summary"] == "블랙과 화이트의 실력이 비슷해요."  # 팀 가명도 실명으로, 조사는 받침에 맞게
    assert len(body["reasons"]) == 3 and not any(r.startswith("P1") for r in body["reasons"])
    # 보낸 입력에는 실명이 없다
    assert not any(name in fake["sent"][0] for name in NAMES)
    # T11: 같은 배정은 다시 부르지 않는다
    again = client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=m).json()
    assert again["cached"] is True and fake["calls"]["A"] == 1
    # 다른 후보안은 새로 부른다
    client.post(f"{API}/assignments/candidates/{run['candidates'][1]['id']}/ai-explanation", headers=m)
    assert fake["calls"]["A"] == 2
    # 팀원은 부를 수 없다
    r = client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=club["members"][2])
    assert r.status_code == 403


def test_explanation_refreshes_when_roster_changes(client, club, fake):
    """T11: 확정 전 선수를 옮기면 명단이 바뀌어 새로 부른다."""
    m = club["manager"]
    eid, _ = _event_with_attendance(client, club)
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    cand = run["candidates"][0]
    client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=m)
    a = cand["squads"][0]["members"][0]["id"]
    b = cand["squads"][1]["members"][0]["id"]
    assert client.patch(f"{API}/assignments/candidates/{cand['id']}", json={"swaps": [{"player_id_a": a, "player_id_b": b}]}, headers=m).status_code == 200
    client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=m)
    assert fake["calls"]["A"] == 2


def test_member_messages_one_call_per_team(client, club, fake):
    """T13: 참석자 전원이 열어도 LLM 호출은 팀 수(2)만큼. 입력에 실력 값이 없다."""
    eid, _, _ = _adopt(client, club)
    seen = set()
    for h in club["members"]:
        r = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fallback"] is False and body["message"]
        seen.add(body["message"])
    assert fake["calls"]["B"] == 2
    assert len(seen) == len(club["members"])  # 사람마다 자기 문장
    for sent in fake["sent"]:
        data = json.loads(sent)
        assert "avg_skill" not in sent and "skill" not in sent
        assert not any(name in sent for name in NAMES)
        assert set(data) == {"team", "players", "team_traits", "mutual_picks"}
    # 받은 문장은 실명으로 돌아와 있고 조사도 받침에 맞다 (예: "이정현은")
    me = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][1]).json()["message"]
    assert me.startswith("이정현은 ")


def test_member_message_leak_falls_back(client, club, fake):
    fake["b_text"] = "{p}는 등급이 높은 편이라 공을 자주 잡아요."
    eid, _, _ = _adopt(client, club)
    body = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][2]).json()
    assert body["fallback"] is True and "등급" not in body["message"]


def test_member_message_requires_adoption(client, club):
    eid, _ = _event_with_attendance(client, club)
    r = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][2])
    assert r.status_code == 404 and r.json()["code"] == "NOT_ADOPTED_YET"
