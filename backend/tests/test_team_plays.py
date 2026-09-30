"""직접 만든 전술 · 역할 자동 추출 · AI 역할 설명 · 전술 댓글 (docs/07 FR-57 ~ FR-60, T17 ~ T21)."""

import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.core.config import get_settings
from app.llm import model as llm_model
from app.llm.prompts import ReasonsD, SlotReasonD
from app.services.team_play_service import spot_name
from app.tactics.extract import ROLE_REASON, extract_roles
from app.tactics.play import Point
from app.tactics.presets import PRESET_LIST, PRESETS
from tests.test_ranking_assignment import _event_with_attendance, club  # noqa: F401

API = "/api/v1"


def P(x, y):
    return {"x": x, "y": y}


def pnr(**over):
    """하이 픽앤롤을 직접 그린 것 — 5번 스크린 → 1번 돌파 · 5번 롤 → 패스 → 슛."""
    body = {
        "name": "우리 픽앤롤", "summary": "", "defense": "man",
        "start": [P(0.5, 0.66), P(0.95, 0.05), P(0.05, 0.05), P(0.15, 0.48), P(0.66, 0.42)], "ball": 1,
        "steps": [
            {"caption": "5번이 1번에게 스크린", "actions": [{"type": "screen", "slot": 5, "to": P(0.57, 0.63), "target": 1}]},
            {"caption": "1번 돌파, 5번 롤", "actions": [
                {"type": "dribble", "slot": 1, "to": P(0.7, 0.4)}, {"type": "cut", "slot": 5, "to": P(0.52, 0.13)},
            ]},
            {"caption": "1번이 5번에게 패스", "actions": [{"type": "pass", "slot": 1, "target": 5}]},
            {"caption": "5번 골밑 슛", "actions": [{"type": "shot", "slot": 5}]},
        ],
        "counter": "{5}가 막히면 코너 {2}에게",
    }
    body.update(over)
    return body


# ---------------------------------------------------------------------------
# T17 역할 자동 추출 (규칙)
# ---------------------------------------------------------------------------


def _roles(key: str) -> list[str]:
    return [r for r, _ in extract_roles(PRESETS[key])]


def test_extract_roles_reads_actions():
    roles = _roles("high_pnr")
    # 움직이지도 공을 받지도 않는 코너는 스페이서 — "킥아웃을 기다리는 슈터" 는 동작에 없는 의도라 매니저가 고친다
    assert roles[0] == "ball_handler" and roles[4] == "screener_roll" and roles[1] == "spacer"
    assert _roles("zone_131")[3] == "cutter"
    assert all(reason for _, reason in extract_roles(PRESETS["horns"]))


def test_extract_roles_screeners():
    assert _roles("post_split")[1] == "cutter"  # 공 없는 동료에게 스크린을 걸고 컷
    assert _roles("box_inbound")[4] == "screener_roll"  # 스크린 뒤 골밑에 남는다
    assert _roles("spain_pnr")[1] == "shooter"  # 코너에서 올라와 백스크린을 걸고 3점 밖으로
    assert _roles("ucla")[4] == "screener_pop"  # 빅맨이 스크린 뒤 탑으로 빠진다


def test_extract_roles_movement():
    assert _roles("zone_screen_flare")[0] == "shooter"  # 공을 넘기고 옮겨 가 다시 받아 3점
    assert _roles("overload")[2] == "shooter"  # 코너로 옮겨 간다
    assert _roles("overload")[4] == "screener_pop"  # 페인트에서 쇼트 코너로 빠진다
    assert _roles("high_low")[3] == "post"  # 하이포스트로 올라와 공을 받는다
    assert _roles("box_inbound")[2] == "spacer"  # 인바운드는 골밑 근처 시작이 빅맨 자리가 아니다


def test_extract_roles_agree_with_presets_mostly():
    """사람이 붙인 프리셋 역할과 80% 이상 같다 (docs/07 O11) — 나머지는 동작에 드러나지 않는 의도라 매니저가 고친다."""
    same = sum(a == b for p in PRESET_LIST for (a, _), b in zip(extract_roles(p), p.roles, strict=True))
    assert same / (5 * len(PRESET_LIST)) >= 0.8


def test_spot_names():
    assert spot_name(Point(x=0.05, y=0.05)) == "왼쪽 코너"
    assert spot_name(Point(x=0.5, y=0.66)) == "탑"
    assert spot_name(Point(x=0.66, y=0.16)) == "오른쪽 블록"
    assert spot_name(Point(x=0.5, y=0.42)) == "자유투 라인"
    assert spot_name(Point(x=0.5, y=-0.05)) == "베이스라인 밖"


# ---------------------------------------------------------------------------
# T18 편집기 — 검사 · 저장 · 권한
# ---------------------------------------------------------------------------


def test_check_and_save_team_play(client, club):
    m, member, tid = club["manager"], club["members"][3], club["team_id"]
    r = client.post(f"{API}/teams/{tid}/plays:check", json=pnr(), headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["playable"] is True and body["errors"] == [] and body["roles"][4] == "screener_roll" and all(body["reasons"])

    # 공 없는 2번이 패스 → 어느 단계가 왜 안 되는지
    bad = pnr(steps=[{"caption": "패스", "actions": [{"type": "pass", "slot": 2, "target": 3}]}])
    r = client.post(f"{API}/teams/{tid}/plays:check", json=bad, headers=m)
    assert r.json()["playable"] is False and "1단계" in r.json()["errors"][0]
    r = client.post(f"{API}/teams/{tid}/plays", json=bad, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "PLAY_NOT_PLAYABLE" and r.json()["details"]
    assert client.post(f"{API}/teams/{tid}/plays", json=pnr(name=" "), headers=m).status_code == 400
    assert client.post(f"{API}/teams/{tid}/plays", json=pnr(steps=[]), headers=m).status_code == 400

    # 팀원도 검사할 수 있다 (v1.7 — 만들기는 아래 권한 테스트)
    assert client.post(f"{API}/teams/{tid}/plays:check", json=pnr(), headers=member).status_code == 200

    r = client.post(f"{API}/teams/{tid}/plays", json=pnr(), headers=m)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["play_key"] == f"team:{created['id']}" and created["play"]["key"] == f"team_{created['id']}"
    assert created["role_source"] == "RULE" and created["play"]["roles"][4] == "screener_roll"
    assert created["play"]["summary"] == "우리 팀이 만든 전술"

    # 팀원은 목록 · 보기만
    listed = client.get(f"{API}/teams/{tid}/plays", headers=member).json()["items"]
    assert [p["id"] for p in listed] == [created["id"]] and listed[0]["can_edit"] is False and listed[0]["mine"] is False
    assert created["mine"] is True and created["can_edit"] is True and created["created_by_name"]
    assert client.get(f"{API}/teams/{tid}/plays/{created['id']}", headers=member).status_code == 200

    # 매니저가 역할을 고쳐 저장 — 출처가 MANAGER
    roles = ["ball_handler", "shooter", "shooter", "spacer", "screener_pop"]
    r = client.put(f"{API}/teams/{tid}/plays/{created['id']}", json=pnr(roles=roles, role_source="MANAGER"), headers=m)
    assert r.status_code == 200 and r.json()["play"]["roles"] == roles and r.json()["role_source"] == "MANAGER"

    # 다른 팀은 볼 수 없다
    other = club["members"][0]  # 매니저 본인이지만 다른 팀을 하나 더 만든다
    other_tid = client.post(f"{API}/teams", json={"name": "다른팀"}, headers=other).json()["id"]
    assert client.get(f"{API}/teams/{other_tid}/plays/{created['id']}", headers=other).status_code == 404


def test_team_play_joins_recommendation_board_and_slots(client, club, monkeypatch):
    from app.services import tactic_service

    monkeypatch.setattr(tactic_service, "FIT_MIN", 0.0)
    monkeypatch.setattr(tactic_service, "TOP_N", 100)
    m, tid = club["manager"], club["team_id"]
    tp = client.post(f"{API}/teams/{tid}/plays", json=pnr(), headers=m).json()
    key = tp["play_key"]
    eid, _ = _event_with_attendance(client, club)
    run = client.post(f"{API}/events/{eid}/assignments", json={"team_count": 2}, headers=m).json()
    assert client.post(f"{API}/assignments/candidates/{run['candidates'][0]['id']}:adopt", headers=m).status_code == 200

    rec = client.get(f"{API}/events/{eid}/tactics/recommend", headers=m).json()
    items = {it["play_key"]: it for it in rec["squads"][0]["items"]}
    assert key in items and "{" not in items[key]["counter"]  # 팀 전술도 추천 후보, 막히면은 이름으로

    view = client.get(f"{API}/events/{eid}/tactics/{key}", headers=m).json()
    assert view["play"]["name"] == "우리 픽앤롤" and view["team_id"] == tid
    sq = view["squads"][0]
    ids = [s["player_id"] for s in sq["lineup"]["slots"]]
    r = client.put(f"{API}/events/{eid}/tactics/{key}/slots", json={"squad_no": sq["squad_no"], "slots": [{"slot": i + 1, "player_id": p} for i, p in enumerate(reversed(ids))]}, headers=m)
    assert r.status_code == 200 and r.json()["squads"][0]["lineup"]["manual"] is True

    # 역할을 바꿔 저장하면 그날 저장한 배치는 지워진다 (다시 자동 추천)
    client.put(f"{API}/teams/{tid}/plays/{tp['id']}", json=pnr(roles=["ball_handler", "shooter", "shooter", "spacer", "post"], role_source="MANAGER"), headers=m)
    assert client.get(f"{API}/events/{eid}/tactics/{key}", headers=m).json()["squads"][0]["lineup"]["manual"] is False

    # 지우면 추천 · 전술판에서 사라진다
    assert client.delete(f"{API}/teams/{tid}/plays/{tp['id']}", headers=m).status_code == 204
    assert client.get(f"{API}/events/{eid}/tactics/{key}", headers=m).status_code == 404
    rec = client.get(f"{API}/events/{eid}/tactics/recommend", headers=m).json()
    assert all(it["play_key"] != key for sq in rec["squads"] for it in sq["items"])


# ---------------------------------------------------------------------------
# T19 · T20 AI 역할 설명 (체인 D) — 역할은 규칙 · 매니저가 정하고 AI 는 이유만 쓴다 (docs/07 O11)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_d(monkeypatch):
    state = {"calls": 0, "sent": [], "drop": False, "odd_number": False}

    def structured(schema, **_kw):
        def respond(messages):
            human = dict(messages)["human"]
            state["sent"].append(human)
            state["calls"] += 1
            data = json.loads(human)
            slots = [SlotReasonD(slot=s["slot"], reason=f"AI 설명 {s['slot']}") for s in data["slots"]]
            if state["odd_number"]:
                slots[1] = SlotReasonD(slot=2, reason="45도 각도에서 기다려요")  # 입력에 없는 숫자 → 가드레일이 비운다
            if state["drop"]:
                slots = slots[:4]
            return ReasonsD(slots=list(reversed(slots)))
        return RunnableLambda(respond)

    monkeypatch.setattr(llm_model, "structured", structured)
    return state


def test_ai_explains_rule_roles_without_changing_them(client, club, fake_d):
    m, tid = club["manager"], club["team_id"]
    rule = client.post(f"{API}/teams/{tid}/plays:check", json=pnr(), headers=m).json()
    r = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(), headers=m)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "AI" and body["fallback"] is False
    assert body["roles"] == rule["roles"]  # 역할은 규칙 그대로
    assert body["reasons"] == [f"AI 설명 {i}" for i in range(1, 6)]  # 자리 순서로 되돌린다
    sent = json.loads(fake_d["sent"][0])
    # 좌표가 아니라 자리 이름만, 선수 정보는 없다. 자리마다 정해진 역할과 규칙이 읽은 근거를 보낸다
    assert sent["slots"][1]["start"] == "오른쪽 코너" and "0.95" not in fake_d["sent"][0]
    assert [x["role"] for x in sent["slots"]] == rule["roles"] and sent["slots"][4]["hint"] == rule["reasons"][4]
    assert "5번 스크린 → 1번에게" in sent["steps"][0]["actions"][0]
    again = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(), headers=m).json()
    assert again["cached"] is True and fake_d["calls"] == 1


def test_ai_blanked_reason_falls_back_per_slot(client, club, fake_d):
    fake_d["odd_number"] = True
    m, tid = club["manager"], club["team_id"]
    rule = client.post(f"{API}/teams/{tid}/plays:check", json=pnr(), headers=m).json()
    body = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(), headers=m).json()
    assert body["fallback"] is False and body["reasons"][0] == "AI 설명 1"
    assert body["reasons"][1] == rule["reasons"][1]  # 비워진 자리만 규칙 이유로


def test_ai_keeps_manager_roles(client, club, fake_d):
    m, tid = club["manager"], club["team_id"]
    rule = client.post(f"{API}/teams/{tid}/plays:check", json=pnr(), headers=m).json()["roles"]
    mine = [*rule[:1], "shooter", *rule[2:]]  # 매니저가 2번(코너)을 슈터로 바꿨다
    body = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(roles=mine, role_source="MANAGER"), headers=m).json()
    assert body["roles"] == mine
    sent = json.loads(fake_d["sent"][0])
    assert sent["slots"][1]["role"] == "shooter" and sent["slots"][1]["hint"] == ""  # 규칙과 다른 자리는 근거 없이 역할만


def test_ai_missing_slot_falls_back_to_rule_reasons(client, club, fake_d):
    fake_d["drop"] = True
    m, tid = club["manager"], club["team_id"]
    body = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(), headers=m).json()
    assert body["source"] == "RULE" and body["fallback"] is True and body["fail_reason"] == "unknown_alias"
    rule = client.post(f"{API}/teams/{tid}/plays:check", json=pnr(), headers=m).json()
    assert body["roles"] == rule["roles"] and body["reasons"] == rule["reasons"]
    # 매니저가 바꾼 자리는 역할 설명 한 줄로
    mine = [*rule["roles"][:1], "shooter", *rule["roles"][2:]]
    body = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(roles=mine), headers=m).json()
    assert body["reasons"][1] == ROLE_REASON["shooter"] and body["reasons"][0] == rule["reasons"][0]


def test_ai_roles_without_key_uses_rule(client, club, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    m, tid = club["manager"], club["team_id"]
    body = client.post(f"{API}/teams/{tid}/plays:ai-roles", json=pnr(), headers=m).json()
    assert body["source"] == "RULE" and body["fail_reason"] == "disabled" and len(body["roles"]) == 5
    bad = pnr(steps=[{"caption": "패스", "actions": [{"type": "pass", "slot": 2, "target": 3}]}])
    assert client.post(f"{API}/teams/{tid}/plays:ai-roles", json=bad, headers=m).status_code == 422


# ---------------------------------------------------------------------------
# T21 전술 댓글
# ---------------------------------------------------------------------------


def test_tactic_comments(client, club, signup):
    m, a, b, tid = club["manager"], club["members"][3], club["members"][4], club["team_id"]
    url = f"{API}/teams/{tid}/tactics/preset:high_pnr/comments"
    r = client.post(url, json={"body": "  2번 코너 자리가 좁아요  "}, headers=a)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["body"] == "2번 코너 자리가 좁아요" and c["mine"] is True and c["can_delete"] is True
    items = client.get(url, headers=b).json()["items"]
    assert len(items) == 1 and items[0]["mine"] is False and items[0]["can_delete"] is False
    assert client.get(url, headers=m).json()["items"][0]["can_delete"] is True  # 매니저는 지울 수 있다

    assert client.post(url, json={"body": "   "}, headers=a).status_code == 400
    assert client.post(f"{API}/teams/{tid}/tactics/preset:nope/comments", json={"body": "?"}, headers=a).status_code == 404
    outsider = signup("out@x.com")
    assert client.get(url, headers=outsider).status_code == 403
    assert client.delete(f"{API}/teams/{tid}/tactic-comments/{c['id']}", headers=b).status_code == 403
    assert client.delete(f"{API}/teams/{tid}/tactic-comments/{c['id']}", headers=m).status_code == 204
    assert client.get(url, headers=a).json()["items"] == []

    # 팀 전술 댓글은 전술을 지우면 함께 지워진다
    tp = client.post(f"{API}/teams/{tid}/plays", json=pnr(), headers=m).json()
    turl = f"{API}/teams/{tid}/tactics/{tp['play_key']}/comments"
    assert client.post(turl, json={"body": "좋아요"}, headers=a).status_code == 201
    client.delete(f"{API}/teams/{tid}/plays/{tp['id']}", headers=m)
    assert client.get(turl, headers=a).status_code == 404


def test_team_play_keeps_assumed_defense_and_may_end_with_move(client, club):
    """편집기에서 고른 상대 수비(지역 · 스위치)가 저장되고, 마지막 단계가 이동이어도 된다 (v1.7)."""
    m, tid = club["manager"], club["team_id"]
    body = pnr(defense=None, opp_defense="zone", screen_call="switch")
    body["steps"] = body["steps"][:2]  # 드리블 · 롤로 끝
    r = client.post(f"{API}/teams/{tid}/plays", json=body, headers=m)
    assert r.status_code == 201, r.text
    play = r.json()["play"]
    assert play["opp_defense"] == "zone" and play["screen_call"] == "switch" and play["defense"] == "zone"
    again = client.get(f"{API}/teams/{tid}/plays/{r.json()['id']}", headers=m).json()["play"]
    assert again["opp_defense"] == "zone" and again["screen_call"] == "switch"


def test_presets_have_fixed_defense():
    assert all(p.opp_defense in ("man", "zone") and p.screen_call in ("switch", "stay") for p in PRESET_LIST)
    assert PRESETS["zone_131"].opp_defense == "zone" and PRESETS["spain_pnr"].screen_call == "switch"
    assert PRESETS["high_pnr"].opp_defense == "man" and PRESETS["high_pnr"].screen_call == "stay"



def test_members_create_and_authors_or_managers_edit(client, club):
    """v1.7: 팀원도 전술을 만든다. 고치기 · 지우기는 만든 사람과 매니저만."""
    m, author, other, tid = club["manager"], club["members"][3], club["members"][4], club["team_id"]
    r = client.post(f"{API}/teams/{tid}/plays", json=pnr(name="팀원 전술"), headers=author)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["mine"] is True and r.json()["can_edit"] is True
    assert client.get(f"{API}/teams/{tid}/plays/{pid}", headers=other).json()["can_edit"] is False
    assert client.get(f"{API}/teams/{tid}/plays/{pid}", headers=m).json()["can_edit"] is True
    # 다른 팀원은 고치거나 지울 수 없다
    assert client.put(f"{API}/teams/{tid}/plays/{pid}", json=pnr(name="몰래"), headers=other).status_code == 403
    assert client.delete(f"{API}/teams/{tid}/plays/{pid}", headers=other).status_code == 403
    # 만든 사람은 고친다, 매니저는 지운다
    assert client.put(f"{API}/teams/{tid}/plays/{pid}", json=pnr(name="고친 전술"), headers=author).json()["play"]["name"] == "고친 전술"
    assert client.delete(f"{API}/teams/{tid}/plays/{pid}", headers=m).status_code == 204
    # 팀원이 만든 것을 만든 사람이 지운다
    pid2 = client.post(f"{API}/teams/{tid}/plays", json=pnr(), headers=author).json()["id"]
    assert client.delete(f"{API}/teams/{tid}/plays/{pid2}", headers=author).status_code == 204


def test_manager_stars_float_to_top(client, club):
    """FR-61: 매니저가 기본 · 팀 전술에 별표. 팀원은 보기만. 팀 전술을 지우면 별표도 사라진다."""
    m, member, tid = club["manager"], club["members"][3], club["team_id"]
    assert client.get(f"{API}/teams/{tid}/tactics/stars", headers=member).json() == {"play_keys": [], "can_edit": False}
    assert client.put(f"{API}/teams/{tid}/tactics/preset:horns/star", headers=member).status_code == 403
    tp = client.post(f"{API}/teams/{tid}/plays", json=pnr(), headers=member).json()
    assert client.put(f"{API}/teams/{tid}/tactics/{tp['play_key']}/star", headers=m).status_code == 200
    r = client.put(f"{API}/teams/{tid}/tactics/preset:horns/star", headers=m)
    assert r.json() == {"play_keys": [tp["play_key"], "preset:horns"], "can_edit": True}
    assert client.put(f"{API}/teams/{tid}/tactics/preset:horns/star", headers=m).json()["play_keys"].count("preset:horns") == 1
    assert client.put(f"{API}/teams/{tid}/tactics/preset:nope/star", headers=m).status_code == 404
    assert client.delete(f"{API}/teams/{tid}/tactics/preset:horns/star", headers=m).json()["play_keys"] == [tp["play_key"]]
    client.delete(f"{API}/teams/{tid}/plays/{tp['id']}", headers=m)
    assert client.get(f"{API}/teams/{tid}/tactics/stars", headers=member).json()["play_keys"] == []
