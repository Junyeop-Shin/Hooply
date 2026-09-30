"""실력 등급 = 같은 팀 활동 회원 안에서의 위치 (분위수, docs 9.2절 표시 정책).

상위 10% A · 다음 20% B · 가운데 40% C · 다음 20% D · 하위 10% E. 게스트는 비교 대상에 넣지 않고 회원들과
비교해 등급만 매긴다. 회원이 5명보다 적으면 절대 구간.
"""

from decimal import Decimal
from itertools import pairwise

from app.schemas.common import SkillGrade
from app.services.player_service import GRADE_CUTS, absolute_grade
from tests.test_ranking_assignment import club  # noqa: F401

API = "/api/v1"
ORDER = "ABCDE"


def _cards(client, club):
    return client.get(f"{API}/teams/{club['team_id']}/players", headers=club["manager"]).json()["items"]


def test_grades_follow_rank_within_team(client, club):
    cards = [c for c in _cards(client, club) if c["kind"] == "MEMBER"]
    by_skill = sorted(cards, key=lambda c: float(c["skill_overall"] if c["skill_overall"] is not None else c["prior_overall"]), reverse=True)
    grades = [c["skill_grade"] for c in by_skill]
    # 실력이 높을수록 등급이 같거나 높다, 맨 위는 A · 맨 아래는 E, 가운데(C)가 가장 많다
    assert all(ORDER.index(a) <= ORDER.index(b) for a, b in pairwise(grades))
    assert grades[0] == "A" and grades[-1] == "E"
    counts = {g: grades.count(g) for g in ORDER}
    assert counts["C"] == max(counts.values())


def test_guest_is_graded_against_members_not_counted(client, club):
    before = {c["id"]: c["skill_grade"] for c in _cards(client, club) if c["kind"] == "MEMBER"}
    eid = client.post(f"{API}/teams/{club['team_id']}/events", json={"event_date": "2026-09-20"}, headers=club["manager"]).json()["id"]
    g = client.post(f"{API}/events/{eid}/guests", json={"display_name": "잘하는게스트", "skill_grade": 5, "force_new": True}, headers=club["manager"])
    assert g.status_code == 201, g.text
    after = _cards(client, club)
    guest = client.get(f"{API}/teams/{club['team_id']}/players?kind=GUEST", headers=club["manager"]).json()["items"][0]
    assert guest["skill_grade"] in ("A", "B")
    assert {c["id"]: c["skill_grade"] for c in after if c["kind"] == "MEMBER"} == before  # 게스트가 와도 회원 등급은 그대로


def test_absolute_fallback_and_cuts():
    assert [g for _, g in GRADE_CUTS] == [SkillGrade.A, SkillGrade.B, SkillGrade.C, SkillGrade.D]
    assert absolute_grade(Decimal("2.0")) == SkillGrade.A and absolute_grade(Decimal("-2.1")) == SkillGrade.E and absolute_grade(0) == SkillGrade.C
