"""온보딩 설문(설문 설계) · 일정/RSVP(F4) · 회차별 게스트(게스트 기능 설계) 흐름.

시나리오: 매니저 1 + 팀원 5 가 팀을 만들고(ACTIVE) 설문에 답한 뒤, 일정을 열고 응답하고,
플레이어가 게스트를 데려오며(묶기 요청), 권한·동명이인·삭제·병합 후보까지 확인한다.
"""

from datetime import UTC, datetime, timedelta

import pytest

API = "/api/v1"


# ---------------------------------------------------------------------------
# 도우미
# ---------------------------------------------------------------------------


def _template(client):
    r = client.get(f"{API}/surveys/onboarding")
    assert r.status_code == 200, r.text
    return r.json()


def _answers(tpl, *, a3="CLUB", b1=("CATCH_SHOOT", "OFFBALL_CUT"), d1=("SF", "SG"), pg="CANNOT", c="CANNOT"):
    """문항 code → 응답 (v2). 기본은 '중간 실력 윙'. d1 은 **선호 순서** (첫 항목이 주 포지션)."""
    pick = {
        "A2": "Y1_3", "A3": a3, "B1": list(b1), "B2": "FT_LINE", "B3": "LIGHT_PRESS",
        "C1": "CHASE", "C2": "HELP_NO_RECOVER", "D1": list(d1), "D3A": pg, "D3B": c,
        "E1": "MOSTLY_OFFBALL", "E2": "Q3_4",
    }
    out = []
    for q in tpl["questions"]:
        codes = pick[q["code"]]
        if isinstance(codes, str):
            codes = [codes]
        by_code = {o["code"]: o["id"] for o in q["options"]}
        ids = [by_code[c] for c in codes]  # 순서 보존 (D1 선호 순서)
        out.append({"question_id": q["id"], "selected_option_ids": ids})
    return out


def _submit(client, headers, tpl, **kw):
    r = client.post(f"{API}/surveys/onboarding/responses", json={"template_id": tpl["template_id"], "answers": _answers(tpl, **kw)}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def team(client, signup):
    """매니저 + 팀원 5명 = 6명 ACTIVE 팀. 반환: dict(manager, members[], team_id, code)."""
    manager = signup("manager@t.com", name="매니저")
    r = client.post(f"{API}/teams", json={"name": "화요농구"}, headers=manager)
    team_id, code = r.json()["id"], r.json()["team_code"]
    members = []
    for i in range(5):
        h = signup(f"m{i}@t.com", name=f"팀원{i}")
        assert client.post(f"{API}/teams/join", json={"team_code": code}, headers=h).status_code == 200
        members.append(h)
    return {"manager": manager, "members": members, "team_id": team_id, "code": code}


def _player_id(client, headers, team_id):
    return client.get(f"{API}/teams/{team_id}", headers=headers).json()["my_player_id"]


# ---------------------------------------------------------------------------
# 설문
# ---------------------------------------------------------------------------


# 검증: v2 템플릿 — 키(A1)·선호 포지션(D2)·상대 위치(E3) 제거, 경기 수준 5단계, 포지션은 선호 순서 다중선택
def test_template_seeded(client):
    tpl = _template(client)
    assert tpl["version"] == 2
    codes = [q["code"] for q in tpl["questions"]]
    assert codes == ["A2", "A3", "B1", "B2", "B3", "C1", "C2", "D1", "D3A", "D3B", "E1", "E2"]
    a3 = next(q for q in tpl["questions"] if q["code"] == "A3")
    assert a3["answer_type"] == "ORDINAL_5"
    assert [o["label"] for o in a3["options"]] == ["체육시간", "동네 야외 농구장", "동호회 혹은 동아리", "아마추어 대회", "선수 출신"]
    d1 = next(q for q in tpl["questions"] if q["code"] == "D1")
    assert "선호하는 순서" in d1["question_text"]
    e2 = next(q for q in tpl["questions"] if q["code"] == "E2")
    assert all(o["label"].endswith("다") for o in e2["options"])  # 문장 형식 통일


# 검증: 스펙 7절 — 형식 오류 400(details 에 문항 코드), 1인 1회 409, 제출 후 onboarding_completed
def test_survey_validation_and_once(client, signup):
    h = signup("s@t.com", name="설문자")
    tpl = _template(client)
    answers = _answers(tpl)
    # 필수 문항 누락 → 400 + 누락 코드
    r = client.post(f"{API}/surveys/onboarding/responses", json={"answers": answers[:-1]}, headers=h)
    assert r.status_code == 400 and r.json()["code"] == "VALIDATION_ERROR"
    assert any("E2" in (d.get("field") or "") for d in r.json()["details"])
    # 단일선택 문항에 2개 → 400
    bad = [dict(a) for a in answers]
    e2 = next(q for q in tpl["questions"] if q["code"] == "E2")
    bad[-1] = {"question_id": e2["id"], "selected_option_ids": [o["id"] for o in e2["options"][:2]]}
    assert client.post(f"{API}/surveys/onboarding/responses", json={"answers": bad}, headers=h).status_code == 400

    prof = _submit(client, h, tpl)
    assert prof["onboarding_completed"] is True and prof["teams"] == []
    # 팀이 없어도 설문의 선호 순서가 프로필에 보인다
    assert prof["playable_positions"] == ["SF", "SG"] and prof["primary_position"] == "SF"
    assert client.get(f"{API}/me", headers=h).json()["onboarding_completed"] is True
    # 재제출 → 409
    r = client.post(f"{API}/surveys/onboarding/responses", json={"answers": answers}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_SUBMITTED"


# 검증: 스펙 5절 — 팀 내 응답자 5명 이상이면 z-score 로 순위가 갈리고, 자기 위치(팀 가입 후 응답) 상위자가
#       높은 등급을 받는다. 설문 → 가입 순서와 가입 → 설문 순서 모두 같은 결과(팀 단위 재계산).
def test_prior_zscore_within_team(client, team):
    tpl = _template(client)
    ranks = ["TOP10", "TOP30", "MID", "BOT30", "BOT10"]
    for h, lvl in zip(team["members"], ranks, strict=True):
        _submit(client, h, tpl, a3="AMATEUR" if lvl.startswith("TOP") else "STREET",
                b1=("CATCH_SHOOT",) if lvl.startswith("BOT") else ("CATCH_SHOOT", "PULLUP", "PNR_HANDLER"))
        # 팀 가입 후에 묻는 "이 동호회에서 내 위치"
        r = client.put(f"{API}/teams/{team['team_id']}/self-rank", json={"level": lvl}, headers=h)
        assert r.status_code == 200 and r.json()["teams"][0]["self_rank_level"] == lvl
    # 매니저는 아직 설문 안 함 → 응답자 5명 → z-score 계산됨
    cards = client.get(f"{API}/teams/{team['team_id']}/players?sort=skill", headers=team["manager"]).json()["items"]
    by_name = {c["display_name"]: c for c in cards}
    top, bot = by_name["팀원0"], by_name["팀원4"]
    assert float(top["prior_overall"]) > 0 > float(bot["prior_overall"])
    assert top["skill_grade"] in ("A", "B") and bot["skill_grade"] in ("D", "E")
    assert by_name["매니저"]["prior_overall"] is None  # 설문 미응답자는 그대로
    # 플레이어 뷰에는 수치가 없다
    p = client.get(f"{API}/teams/{team['team_id']}/players", headers=team["members"][0]).json()["items"][0]
    assert "prior_overall" not in p
    # 내 프로필: 팀별 등급 + 응답자 수
    me = client.get(f"{API}/me/profile", headers=team["members"][0]).json()
    assert me["teams"][0]["survey_sample_size"] == 5 and me["teams"][0]["prior_source"] == "SURVEY"
    assert me["playable_positions"] == ["SF", "SG"] and me["primary_position"] == "SF"  # 선호 순서대로


# 검증: D1 선택 순서 = 선호 순서, D3 응답이 하드 제약(PG/C)에 반영, PUT /me/positions 는 목록 순서를 선호 순서로 저장
def test_positions_from_survey_and_update(client, signup, team):
    tpl = _template(client)
    h = team["members"][0]
    _submit(client, h, tpl, d1=("SF", "PF"), pg="CAN_PREFER", c="CANNOT")
    me = client.get(f"{API}/me/profile", headers=h).json()
    assert me["playable_positions"] == ["SF", "PF", "PG"] and me["primary_position"] == "SF"  # PG 는 D3 로 추가 → 맨 뒤
    # 프로필에서 선호 순서 변경: 목록 순서가 곧 순위
    r = client.put(f"{API}/me/positions", json={"positions": [{"position": "C"}, {"position": "SF"}]}, headers=h)
    assert r.status_code == 200 and r.json()["playable_positions"] == ["C", "SF"] and r.json()["primary_position"] == "C"
    r = client.put(f"{API}/me/positions", json={"positions": [{"position": "C"}, {"position": "C"}]}, headers=h)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 일정 · RSVP
# ---------------------------------------------------------------------------


# 검증: FR-06/08/09 — PENDING 팀은 422, 등록 시 회원 전원 PENDING, 응답·마감·취소
def test_event_and_rsvp(client, signup, team):
    m, tid = team["manager"], team["team_id"]
    # 4명짜리 팀은 일정 불가
    other = signup("o@t.com", name="다른팀장")
    small = client.post(f"{API}/teams", json={"name": "소규모"}, headers=other).json()["id"]
    r = client.post(f"{API}/teams/{small}/events", json={"event_date": "2026-09-15"}, headers=other)
    assert r.status_code == 422 and r.json()["code"] == "TEAM_NOT_ACTIVE"
    # 플레이어는 등록 불가
    assert client.post(f"{API}/teams/{tid}/events", json={"event_date": "2026-09-15"}, headers=team["members"][0]).status_code == 403

    deadline = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    r = client.post(f"{API}/teams/{tid}/events", json={"title": "화요 정기전", "event_date": "2026-09-15", "start_time": "20:00", "end_time": "22:00", "venue": "서초체육관", "rsvp_deadline": deadline}, headers=m)
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["status"] == "OPEN" and ev["attend_count"] == 0 and ev["my_attendance"] == "PENDING" and ev["rsvp_open"]
    eid = ev["id"]

    att = client.get(f"{API}/events/{eid}/attendances", headers=m).json()
    assert att["summary"]["pending"] == 6 and len(att["items"]) == 6

    # 응답
    r = client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND", "note": "늦게 감"}, headers=team["members"][0])
    assert r.status_code == 200 and r.json()["status"] == "ATTEND" and r.json()["registered_by"] is None
    for h in team["members"][1:4]:
        client.put(f"{API}/events/{eid}/attendance", json={"status": "ATTEND"}, headers=h)
    client.put(f"{API}/events/{eid}/attendance", json={"status": "ABSENT"}, headers=team["members"][4])
    ev = client.get(f"{API}/events/{eid}", headers=team["members"][0]).json()
    assert ev["attend_count"] == 4 and ev["my_attendance"] == "ATTEND"
    s = client.get(f"{API}/events/{eid}/attendances?status=ATTEND", headers=m).json()
    assert len(s["items"]) == 4 and s["summary"]["absent"] == 1 and s["summary"]["pending"] == 1
    # 포지션 분포는 사람당 '가장 선호하는 포지션' 하나만 센다 (설문 안 한 팀원은 어디에도 안 들어감)
    assert sum(s["summary"]["position_counts"].values()) <= s["summary"]["attend"]
    assert any("최소 10명" in w for w in s["summary"]["warnings"])

    # 목록 (홈 카드)
    lst = client.get(f"{API}/teams/{tid}/events", headers=team["members"][0]).json()
    assert lst["meta"]["total"] == 1 and lst["items"][0]["my_attendance"] == "ATTEND"

    # 마감 지나면 본인 응답 불가, 매니저 대리 응답은 가능
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert client.patch(f"{API}/events/{eid}", json={"rsvp_deadline": past}, headers=m).status_code == 200
    r = client.put(f"{API}/events/{eid}/attendance", json={"status": "ABSENT"}, headers=team["members"][0])
    assert r.status_code == 422 and r.json()["code"] == "RSVP_CLOSED"
    pid = _player_id(client, team["members"][0], tid)
    r = client.put(f"{API}/events/{eid}/attendances/{pid}", json={"status": "ABSENT"}, headers=m)
    assert r.status_code == 200 and r.json()["registered_by"] is not None

    # 삭제 — 상태만 바꾸지 않고 일정이 사라진다
    assert client.delete(f"{API}/events/{eid}", headers=m).status_code == 204
    assert client.get(f"{API}/events/{eid}", headers=m).status_code == 404
    assert client.get(f"{API}/teams/{tid}/events", headers=m).json()["meta"]["total"] == 0


# ---------------------------------------------------------------------------
# 회차별 게스트
# ---------------------------------------------------------------------------


@pytest.fixture
def event(client, team):
    r = client.post(f"{API}/teams/{team['team_id']}/events", json={"event_date": "2026-09-22"}, headers=team["manager"])
    assert r.status_code == 201
    return r.json()["id"]


# 검증: 스펙 FR-10/11/11a — 플레이어가 등급·포지션·묶기 요청과 함께 게스트 등록, 요약과 제안 반영
def test_player_registers_guest_with_lock_request(client, team, event):
    p1 = team["members"][0]
    p1_pid = _player_id(client, p1, team["team_id"])
    client.put(f"{API}/events/{event}/attendance", json={"status": "ATTEND"}, headers=p1)
    r = client.post(f"{API}/events/{event}/guests", json={"display_name": "김게스트", "skill_grade": 4, "preferred_position": "SF", "playable_positions": ["SF", "PF"], "team_lock_request": True}, headers=p1)
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["player"]["kind"] == "GUEST" and g["status"] == "ATTEND" and g["can_edit"] is True
    assert g["team_lock_request_player_id"] == p1_pid and g["player"]["primary_position"] == "SF"
    assert set(g["player"]["playable_positions"]) == {"SF", "PF"}
    assert g["player"]["skill_grade"] is None  # 플레이어에게는 등급이 보이지 않는다 (매니저 전용)
    mgr_items = client.get(f"{API}/events/{event}/attendances", headers=team["manager"]).json()["items"]
    assert next(i for i in mgr_items if i["player"]["id"] == g["player"]["id"])["player"]["skill_grade"] is not None

    # 등급 미지정 게스트 → confidence 0. 요약에는 게스트 평균 가정 문구를 넣지 않는다 (초대 시트에서 안내)
    r = client.post(f"{API}/events/{event}/guests", json={"display_name": "박무명"}, headers=p1)
    assert r.status_code == 201 and float(r.json()["player"]["skill_confidence"]) == 0
    s = client.get(f"{API}/events/{event}/attendances", headers=p1).json()["summary"]
    assert s["attend"] == 3 and s["guest_count"] == 2
    assert not any("게스트" in w for w in s["warnings"])

    # 게스트는 회차 화면에서만 보인다: 팀원 목록 기본 조회에 안 나온다 (kind=GUEST 를 명시해야 나옴)
    names = [c["display_name"] for c in client.get(f"{API}/teams/{team['team_id']}/players", headers=team["manager"]).json()["items"]]
    assert "김게스트" not in names
    assert "김게스트" in [c["display_name"] for c in client.get(f"{API}/teams/{team['team_id']}/players?kind=GUEST", headers=team["manager"]).json()["items"]]

    # 초대 이력(불러오기): 등록자 본인에게만, 입력했던 값 그대로 + 레코드 재사용 id
    presets = client.get(f"{API}/events/{event}/guests/presets", headers=p1).json()["items"]
    assert [p["display_name"] for p in presets] == ["박무명", "김게스트"]  # 최근 사용순
    kim = presets[1]
    assert kim["skill_grade"] == 4 and kim["preferred_position"] == "SF" and set(kim["playable_positions"]) == {"SF", "PF"}
    assert kim["team_lock_request"] is True and kim["existing_player_id"] == g["player"]["id"]
    assert client.get(f"{API}/events/{event}/guests/presets", headers=team["members"][1]).json()["items"] == []

    # 매니저의 묶기 제안: 게스트·대상 모두 ATTEND 인 1건
    sug = client.get(f"{API}/events/{event}/assignment/suggestions", headers=team["manager"]).json()["items"]
    assert len(sug) == 1 and sug[0]["guest"]["display_name"] == "김게스트" and sug[0]["target"]["id"] == p1_pid
    # 대상이 불참으로 바뀌면 제안 무효 (스펙 7절)
    client.put(f"{API}/events/{event}/attendance", json={"status": "ABSENT"}, headers=p1)
    assert client.get(f"{API}/events/{event}/assignment/suggestions", headers=team["manager"]).json()["items"] == []
    # 플레이어는 제안 조회 불가
    assert client.get(f"{API}/events/{event}/assignment/suggestions", headers=p1).status_code == 403


# 검증: 스펙 FR-10a · 7절 — 등록자/매니저만 수정·삭제, 남은 게스트 레코드는 재사용(FR-12), 삭제는 참석 행만
def test_guest_ownership_and_reuse(client, team, event):
    p1, p2, m = team["members"][0], team["members"][1], team["manager"]
    gid = client.post(f"{API}/events/{event}/guests", json={"display_name": "이초대"}, headers=p1).json()["player"]["id"]

    # 다른 플레이어 → 403 FORBIDDEN_NOT_OWNER
    r = client.patch(f"{API}/events/{event}/guests/{gid}", json={"skill_grade": 2}, headers=p2)
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN_NOT_OWNER"
    assert client.delete(f"{API}/events/{event}/guests/{gid}", headers=p2).status_code == 403
    assert client.patch(f"{API}/players/{gid}", json={"display_name": "x"}, headers=p2).status_code == 403
    # 다른 플레이어 뷰에서는 can_edit=false, 매니저 뷰에서는 true
    items = client.get(f"{API}/events/{event}/attendances", headers=p2).json()["items"]
    assert next(i for i in items if i["player"]["id"] == gid)["can_edit"] is False
    items = client.get(f"{API}/events/{event}/attendances", headers=m).json()["items"]
    assert next(i for i in items if i["player"]["id"] == gid)["can_edit"] is True

    # 등록자 수정 (등급 + 묶기 요청 켜기), 매니저 수정
    r = client.patch(f"{API}/events/{event}/guests/{gid}", json={"skill_grade": 5, "team_lock_request": True}, headers=p1)
    assert r.status_code == 200 and r.json()["team_lock_request_player_id"] == _player_id(client, p1, team["team_id"])
    r = client.patch(f"{API}/events/{event}/guests/{gid}", json={"display_name": "이초대(수정)", "team_lock_request": False}, headers=m)
    assert r.status_code == 200 and r.json()["player"]["display_name"] == "이초대(수정)" and r.json()["team_lock_request_player_id"] is None

    # 삭제: 참석 행만 사라지고 레코드는 검색됨
    assert client.delete(f"{API}/events/{event}/guests/{gid}", headers=p1).status_code == 204
    assert all(i["player"]["id"] != gid for i in client.get(f"{API}/events/{event}/attendances", headers=m).json()["items"])
    found = client.get(f"{API}/teams/{team['team_id']}/guests?q=초대", headers=p2).json()["items"]
    assert [g["id"] for g in found] == [gid]

    # 동명이인: 같은 이름으로 다시 등록하면 200 + similar, existing_player_id 로 재사용하면 201
    r = client.post(f"{API}/events/{event}/guests", json={"display_name": "이초대(수정)"}, headers=p2)
    assert r.status_code == 200 and r.json()["similar"][0]["id"] == gid
    r = client.post(f"{API}/events/{event}/guests", json={"display_name": "이초대(수정)", "existing_player_id": gid}, headers=p2)
    assert r.status_code == 201 and r.json()["player"]["id"] == gid
    # force_new 면 새 레코드
    r = client.post(f"{API}/events/{event}/guests", json={"display_name": "이초대(수정)", "force_new": True}, headers=p2)
    assert r.status_code == 201 and r.json()["player"]["id"] != gid


# 검증: FR-13 + 사용자 요청 — 게스트와 같은 이름으로 가입한 회원을 병합 후보로 보여주고, 매니저가 병합·되돌리기
def test_merge_candidates_and_merge(client, signup, team, event):
    m, p1 = team["manager"], team["members"][0]
    gid = client.post(f"{API}/events/{event}/guests", json={"display_name": "최단골", "skill_grade": 3}, headers=p1).json()["player"]["id"]
    # 같은 이름으로 회원가입 후 팀 가입
    newbie = signup("choi@t.com", name="최단골")
    client.post(f"{API}/teams/join", json={"team_code": team["code"]}, headers=newbie)
    new_pid = _player_id(client, newbie, team["team_id"])

    assert client.get(f"{API}/teams/{team['team_id']}/guests/merge-candidates", headers=p1).status_code == 403
    cands = client.get(f"{API}/teams/{team['team_id']}/guests/merge-candidates", headers=m).json()["items"]
    assert len(cands) == 1 and cands[0]["guest"]["id"] == gid and cands[0]["member"]["id"] == new_pid

    # 병합: 플레이어 불가, 매니저 가능, 두 번째는 409, 되돌리기
    assert client.post(f"{API}/players/{gid}:merge", json={"into_player_id": new_pid}, headers=p1).status_code == 403
    r = client.post(f"{API}/players/{gid}:merge", json={"into_player_id": new_pid}, headers=m)
    assert r.status_code == 200 and r.json()["id"] == new_pid
    assert client.get(f"{API}/teams/{team['team_id']}/guests", headers=m).json()["items"] == []  # LEFT 로 빠짐
    r = client.post(f"{API}/players/{gid}:merge", json={"into_player_id": new_pid}, headers=m)
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_MERGED"
    assert client.post(f"{API}/players/{gid}:unmerge", headers=m).status_code == 200
    assert [g["id"] for g in client.get(f"{API}/teams/{team['team_id']}/guests", headers=m).json()["items"]] == [gid]
    # 회원을 병합 출발지로 쓰면 400, 다른 종류 대상이면 422
    assert client.post(f"{API}/players/{new_pid}:merge", json={"into_player_id": gid}, headers=m).status_code == 400
    r = client.post(f"{API}/players/{gid}:merge", json={"into_player_id": gid}, headers=m)
    assert r.status_code == 422 and r.json()["code"] == "MERGE_KIND_MISMATCH"
