"""AI 배정 설명 체인 A(매니저) · B(팀원) (docs/07 FR-51, T10 · T11 · T13).

모델 자리에 LangChain Runnable 을 끼워 고정 결과를 돌려준다 (CI 에 키가 없다). 보낸 입력에 실명·실력 값이 없는지도 확인한다.
"""

import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.core.config import get_settings
from app.llm import model as llm_model
from app.llm.prompts import ExplainA, PlayerMessage, TacticItemC, TacticsC, TeamMessagesB
from tests.test_ranking_assignment import ROSTER, _event_with_attendance, club  # noqa: F401

API = "/api/v1"
NAMES = [r[0] for r in ROSTER]


@pytest.fixture
def fake(monkeypatch):
    """체인에 따라 입력의 판단을 그대로 옮긴 고정 결과를 돌려준다. sent 에 보낸 human 메시지를 모은다."""
    state = {"calls": {"A": 0, "B": 0, "C": 0}, "sent": [], "leak": False, "c_extra": None}

    def structured(schema, **_kw):
        def respond(messages):
            human = dict(messages)["human"]
            state["sent"].append(human)
            data = json.loads(human)
            if schema is ExplainA:
                state["calls"]["A"] += 1
                teams = data["teams"]
                return ExplainA(
                    summary="A와 B가 고르게 나뉜 구성이에요.",
                    key_players=[f"{t['team']} · {k['player']} — {k['role']}로 활약이 기대돼요" for t in teams for k in t["key_players"]],
                    chemistry=[f"{t['team']} · {p['players'][0]}과 {p['players'][1]} — {p['why']}" for t in teams for p in t["pairs"]],
                    gaps=[f"{t['team']} · {g}가 부족해요" for t in teams for g in t["gaps"]],
                    watch_point="",
                )
            if schema is TacticsC:
                state["calls"]["C"] += 1
                recs = data["recommendations"]
                items = [
                    TacticItemC(
                        play_id=r["play_id"], reason=f"{r['slots'][0]['player']}의 {r['slots'][0]['role']} 역할이 살아나요.",
                        key_roles=[f"{s['player']} — {s['role']}" for s in r["slots"][:3]], caution="",
                    )
                    for r in recs
                ]
                items = list(reversed(items[1:]))  # 첫 전술은 빠뜨리고 순서도 뒤집어 보낸다
                if state["c_extra"]:
                    items.append(TacticItemC(play_id=state["c_extra"], reason="없는 전술", key_roles=[], caution=""))
                return TacticsC(one_liner=f"{data['team']}는 골밑과 외곽이 고르게 살아나는 구성이에요.", items=items)
            state["calls"]["B"] += 1
            return TeamMessagesB(messages=[
                PlayerMessage(
                    player=p["id"],
                    why_position=f"{p['id']}님은 {p['position_why'][0] if p['position_why'] else '팀 구성상'} 자리예요.",
                    role=("등급이 높은 편이라 " if state["leak"] else "") + f"{p['role']} 역할이 기대돼요.",
                    partner=f"{p['partners'][0]['with']}와 {p['partners'][0]['why']}를 맞춰 보세요." if p["partners"] else "",
                )
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
    assert body["fallback"] is True and body["text"] == cand["explanation"] and body["key_players"] == []
    r = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][3])
    assert r.status_code == 200 and r.json()["fallback"] is True and r.json()["text"]


def test_manager_explanation_uses_aliases_and_restores(client, club, fake):
    m = club["manager"]
    _, run, cand = _adopt(client, club)
    r = client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fallback"] is False and body["cached"] is False and body["text"] is None
    assert body["summary"] == "블랙과 화이트가 고르게 나뉜 구성이에요."  # 팀 가명도 실명으로, 조사는 받침에 맞게
    assert body["key_players"] and all(k.startswith(("블랙 · ", "화이트 · ")) for k in body["key_players"])
    assert not any("P" in c.split("—")[0] for c in body["chemistry"])  # 가명이 남지 않는다
    # 보낸 입력: 실명 없음, 판단 재료(활약 · 조합 · 부족한 역할)는 들어 있다
    sent = json.loads(fake["sent"][0])
    assert not any(name in fake["sent"][0] for name in NAMES)
    assert {"key_players", "pairs", "gaps"} <= set(sent["teams"][0])
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
        assert body["fallback"] is False and body["role"] and body["why_position"]
        seen.add(body["why_position"])
    assert fake["calls"]["B"] == 2
    assert len(seen) == len(club["members"])  # 사람마다 자기 문장
    for sent in fake["sent"]:
        data = json.loads(sent)
        assert "skill" not in sent and "avg" not in sent  # 실력 값 없음
        assert not any(name in sent for name in NAMES)
        assert set(data) == {"team", "players"}
        assert set(data["players"][0]) == {"id", "position", "position_why", "role", "strengths", "partners"}
    # 받은 문장은 실명으로 돌아와 있다
    me = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][1]).json()
    assert me["why_position"].startswith("이정현님은 ")


def test_member_message_leak_falls_back(client, club, fake):
    fake["leak"] = True
    eid, _, _ = _adopt(client, club)
    body = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][2]).json()
    assert body["fallback"] is True and body["role"] == "" and "등급" not in (body["text"] or "")


def test_member_message_requires_adoption(client, club):
    eid, _ = _event_with_attendance(client, club)
    r = client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][2])
    assert r.status_code == 404 and r.json()["code"] == "NOT_ADOPTED_YET"


def test_insight_pairs_gaps_and_position_reasons(client, club, fake, monkeypatch):
    """판단은 규칙이 한다: 역할 궁합(픽앤롤 등) · 상호 지목 · 부족한 역할 · 포지션 이유가 입력에 들어간다."""
    from collections import defaultdict

    from app.services import ai_insight
    from app.tactics.play import ROLES
    from app.tactics.roles import PlayerRoles

    cycle = ["ball_handler", "screener_roll", "shooter", "post", "cutter", "spacer"]

    def fake_scores(_db, _event, players):
        out = {}
        for i, pid in enumerate(sorted(players)):
            top = cycle[i % len(cycle)]
            out[pid] = PlayerRoles(player_id=pid, scores={r: (0.9 if r == top else 0.3) for r in ROLES}, terms=defaultdict(float))
        return out

    monkeypatch.setattr(ai_insight, "role_scores_for", fake_scores)
    eid, _, cand = _adopt(client, club)
    client.post(f"{API}/assignments/candidates/{cand['id']}/ai-explanation", headers=club["manager"])
    sent = json.loads(fake["sent"][-1])
    whys = {p["why"] for t in sent["teams"] for p in t["pairs"]}
    assert whys & {"픽앤롤", "인사이드-아웃", "돌파 후 킥아웃 3점", "컷인 패스", "포스트에서 컷인 패스", "스크린으로 슈터 살리기"}
    for t in sent["teams"]:
        assert all(g in ai_insight.ROLE_KO.values() for g in t["gaps"])
        assert len(t["key_players"]) <= 2

    client.get(f"{API}/events/{eid}/assignment/adopted/ai-message", headers=club["members"][1])
    team = json.loads(fake["sent"][-1])
    p = team["players"][0]
    assert p["position_why"] and p["role"] in ai_insight.ROLE_KO.values()
    assert all(q["with"].startswith("P") for q in p["partners"]) and len(p["partners"]) <= 2


@pytest.fixture
def low_fit(monkeypatch):
    """club 픽스처는 모두 같은 설문이라 적합도가 낮다 — 추천이 나오게 기준을 내린다."""
    from app.services import tactic_service

    monkeypatch.setattr(tactic_service, "FIT_MIN", 0.0)


def test_tactics_explanation_keeps_order_and_fills_missing(client, club, fake, low_fit):
    eid, _, _ = _adopt(client, club)
    rec = client.get(f"{API}/events/{eid}/tactics/recommend", headers=club["members"][3]).json()["squads"][0]
    r = client.post(f"{API}/events/{eid}/tactics/ai-recommend", params={"squad_no": 1}, headers=club["members"][3])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fallback"] is False and body["one_liner"].startswith("블랙은 ")  # 팀 가명 복원 + 받침에 맞는 조사
    # 추천 순서 그대로, AI 가 빠뜨린 첫 전술은 규칙 문장으로
    assert [it["play_key"] for it in body["items"]] == [it["play_key"] for it in rec["items"]]
    assert body["items"][0]["reason"].startswith("적합도 ") and body["items"][0]["key_roles"] == []
    assert body["items"][1]["key_roles"] and not any("P" in k.split(" — ")[0] for k in body["items"][1]["key_roles"])
    sent = json.loads(fake["sent"][-1])
    assert not any(name in fake["sent"][-1] for name in NAMES)
    assert "score" not in fake["sent"][-1]  # 자리별 점수는 보내지 않는다
    assert [x["play_id"] for x in sent["recommendations"]] == [it["play_key"].removeprefix("preset:") for it in rec["items"]]
    # 같은 팀 · 같은 수비 보기는 다시 부르지 않는다
    again = client.post(f"{API}/events/{eid}/tactics/ai-recommend", params={"squad_no": 1}, headers=club["manager"]).json()
    assert again["cached"] is True and fake["calls"]["C"] == 1


def test_tactics_explanation_unknown_play_falls_back(client, club, fake, low_fit):
    fake["c_extra"] = "iso_everyone"
    eid, _, _ = _adopt(client, club)
    body = client.post(f"{API}/events/{eid}/tactics/ai-recommend", params={"squad_no": 2}, headers=club["manager"]).json()
    assert body["fallback"] is True and all(it["reason"].startswith("적합도 ") for it in body["items"])


def test_tactics_explanation_permissions(client, club, signup, low_fit, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    eid, _, _ = _adopt(client, club)
    r = client.post(f"{API}/events/{eid}/tactics/ai-recommend", params={"squad_no": 1}, headers=club["members"][4])
    assert r.status_code == 200 and r.json()["fallback"] is True  # 키 없음 → 규칙 문장
    team = client.get(f"{API}/teams/{club['team_id']}", headers=club["manager"]).json()
    outsider = signup("late2@club.com", name="늦게온사람")
    client.post(f"{API}/teams/join", json={"team_code": team["team_code"]}, headers=outsider)
    r = client.post(f"{API}/events/{eid}/tactics/ai-recommend", params={"squad_no": 1}, headers=outsider)
    assert r.status_code == 403 and r.json()["code"] == "NOT_ATTENDEE"
    assert client.post(f"{API}/events/{eid}/tactics/ai-recommend", params={"squad_no": 9}, headers=club["manager"]).status_code == 404
