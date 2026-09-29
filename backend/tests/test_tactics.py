"""전술 추천 1단계: 좌표 판정 · 재생 가능성 검사 · 역할 점수 · 슬롯 최적 배치 (docs/07 T1~T4).

DB 없이 돌아가는 순수 계산만 검사한다. 프리셋 14개의 재생 검사(T2 앞부분)는 tests/test_tactics_api.py 에 있다.
"""

import itertools
import random

import pytest
from pydantic import ValidationError

from app.tactics.court import is_paint, is_three, rim_distance, zone_of
from app.tactics.matching import best_lineup, fit_play, rank_plays
from app.tactics.play import ROLES, Play, holders, playability_errors
from app.tactics.roles import (
    NO_SURVEY,
    NO_SURVEY_GUEST,
    TERM_LABEL,
    PlayerRoles,
    RoleInput,
    compute_role_scores,
)

# ---------------------------------------------------------------------------
# T1 좌표 판정 (명세 8.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("x", "y", "zone"), [
    (0.06, 0.1, "three"),  # 왼쪽 코너, 좌우 6.6m 딱 경계
    (0.94, 0.1, "three"),  # 오른쪽 코너
    (0.5, 0.60, "three"),  # 탑, 림 거리 ≈ 6.83m
    (0.5, 0.55, "mid"),  # 탑 3점 안쪽
    (0.5, 0.3, "paint"),  # 자유투 라인 아래 가운데
    (0.5, 0.0, "paint"),  # 림 바로 뒤 베이스라인
    (0.07, 0.1, "mid"),  # 코너 3점 라인 한 발 안
])
def test_zone_boundaries(x, y, zone):
    assert zone_of(x, y) == zone


def test_top_of_key_distance():
    assert rim_distance(0.5, 0.60) == pytest.approx(6.825, abs=1e-3)


def test_corner_inside_line_near_baseline_is_not_three():
    # 좌우 6.58m · 베이스라인 위: 림까지 거리는 6.75m 를 넘지만 코너 직선 안쪽이라 2점
    x = (7.5 - 6.58) / 15
    assert rim_distance(x, 0.0) > 6.75
    assert not is_three(x, 0.0)


def test_paint_edges():
    assert is_paint((7.5 + 2.45) / 15, 5.8 / 14)  # 오른쪽 위 모서리 (선 위 포함)
    assert not is_paint((7.5 + 2.5) / 15, 0.2)
    assert not is_paint(0.5, 6.0 / 14)


# ---------------------------------------------------------------------------
# T2 재생 가능성 검사 (FR-38, FR-39, FR-41)
# ---------------------------------------------------------------------------


def _pnr(**over) -> dict:
    """하이 픽앤롤 뼈대: ① 탑(공) ② 오른쪽 코너 ③ 왼쪽 코너 ④ 왼쪽 윙 ⑤ 오른쪽 엘보."""
    play = {
        "key": "test_pnr",
        "name": "테스트 픽앤롤",
        "summary": "5번이 올라와 스크린, 1번 돌파 후 롤맨에게",
        "defense": "man",
        "start": [
            {"x": 0.5, "y": 0.62}, {"x": 0.95, "y": 0.05}, {"x": 0.05, "y": 0.05},
            {"x": 0.12, "y": 0.45}, {"x": 0.66, "y": 0.42},
        ],
        "ball": 1,
        "roles": ["ball_handler", "shooter", "shooter", "spacer", "screener_roll"],
        "steps": [
            {"caption": "5번이 탑으로 올라와 1번에게 스크린",
             "actions": [{"type": "screen", "slot": 5, "to": {"x": 0.56, "y": 0.6}, "target": 1}]},
            {"caption": "1번 드리블 돌파, 5번 림으로 롤",
             "actions": [{"type": "dribble", "slot": 1, "to": {"x": 0.62, "y": 0.4}},
                         {"type": "cut", "slot": 5, "to": {"x": 0.52, "y": 0.18}}]},
            {"caption": "1번이 5번에게 패스",
             "actions": [{"type": "pass", "slot": 1, "target": 5}]},
            {"caption": "5번 골밑 슛", "actions": [{"type": "shot", "slot": 5}]},
        ],
    }
    play.update(over)
    return play


def test_valid_play_passes_and_ball_follows_passes():
    play = Play.model_validate(_pnr())
    assert playability_errors(play) == []
    assert holders(play) == [1, 1, 1, 5, None]


def test_pass_from_slot_without_ball_is_rejected():
    raw = _pnr()
    raw["steps"][2]["actions"] = [{"type": "pass", "slot": 3, "target": 5}]
    errors = playability_errors(Play.model_validate(raw))
    assert "3단계: 3번은 공이 없어 패스할 수 없어요 (공은 1번)" in errors


@pytest.mark.parametrize(("step_no", "actions", "message"), [
    (2, [{"type": "cut", "slot": 1, "to": {"x": 0.5, "y": 0.2}}],
     "2단계: 공을 가진 1번은 컷 대신 드리블로 움직여요"),
    (2, [{"type": "dribble", "slot": 1, "to": {"x": 0.6, "y": 0.4}},
         {"type": "pass", "slot": 1, "target": 2}],
     "2단계: 공 동작은 한 단계에 하나만 할 수 있어요"),
    (1, [{"type": "move", "slot": 4, "to": {"x": 0.2, "y": 0.5}},
         {"type": "cut", "slot": 4, "to": {"x": 0.3, "y": 0.2}}],
     "1단계: 4번이 동작을 두 개 해요. 단계를 나눠 주세요"),
])
def test_rule_violations_name_the_step(step_no, actions, message):
    raw = _pnr()
    raw["steps"][step_no - 1]["actions"] = actions
    assert message in playability_errors(Play.model_validate(raw))


def test_must_end_with_shot_or_pass_and_nothing_after_shot():
    raw = _pnr()
    raw["steps"] = raw["steps"][:2]  # 드리블·롤에서 끝남
    assert "2단계: 마지막 단계는 슛이나 패스로 끝나야 해요" in playability_errors(Play.model_validate(raw))

    raw = _pnr()
    raw["steps"].append({"caption": "슛 뒤 이동", "actions": [{"type": "move", "slot": 2, "to": {"x": 0.9, "y": 0.3}}]})
    assert "5단계: 앞 단계에서 슛을 해 공이 없어요" in playability_errors(Play.model_validate(raw))


@pytest.mark.parametrize("bad", [
    {"type": "pass", "slot": 1},  # 받는 사람 없음
    {"type": "dribble", "slot": 1, "target": 2, "to": {"x": 0.5, "y": 0.5}},  # 드리블에 대상
    {"type": "shot", "slot": 1, "to": {"x": 0.5, "y": 0.1}},  # 슛에 도착 위치
    {"type": "screen", "slot": 5, "to": {"x": 0.5, "y": 0.5}, "target": 5},  # 자기에게 스크린
    {"type": "jump", "slot": 1},  # 없는 동작 (FR-39)
    {"type": "move", "slot": 6, "to": {"x": 0.5, "y": 0.5}},  # 없는 슬롯
    {"type": "move", "slot": 1, "to": {"x": 1.2, "y": 0.5}},  # 코트 밖 좌표
    {"type": "move", "slot": 1, "to": {"x": 0.5, "y": -0.2}},  # 베이스라인 뒤로 너무 멀리 (인바운드 자리는 -0.08 까지)
])
def test_malformed_actions_fail_validation(bad):
    raw = _pnr()
    raw["steps"][0]["actions"] = [bad]
    with pytest.raises(ValidationError):
        Play.model_validate(raw)


@pytest.mark.parametrize("field", ["start", "roles", "steps", "defense", "ball"])
def test_missing_required_field_fails(field):
    raw = _pnr()
    del raw[field]
    with pytest.raises(ValidationError):
        Play.model_validate(raw)


# ---------------------------------------------------------------------------
# 역할 점수 (FR-43, 7절)
# ---------------------------------------------------------------------------


def _guard(pid: int) -> RoleInput:
    return RoleInput(
        player_id=pid, height_cm=172, positions=frozenset({"PG", "SG"}), has_survey=True,
        b1=frozenset({"PNR_HANDLER", "PULLUP", "CATCH_SHOOT"}), shot_range=0.75, handle=1.0, passing=0.8, stamina=0.6,
    )


def _big(pid: int) -> RoleInput:
    return RoleInput(
        player_id=pid, height_cm=192, positions=frozenset({"PF", "C"}), has_survey=True,
        b1=frozenset({"POST_UP", "PNR_ROLL_POP", "PUTBACK"}), shot_range=0.25, handle=0.0, passing=0.3, stamina=0.5,
    )


def test_role_scores_follow_the_formula():
    scores = compute_role_scores([_guard(1), _big(2)])
    g, b = scores[1], scores[2]
    # 가드: .40·1 + .30·1 + .15·1 + .15·.8
    assert g.scores["ball_handler"] == pytest.approx(0.97)
    # 빅맨: 키 백분위 1 → .35 + .25 + .20·max(풋백 1, 돌파 0) + .20
    assert b.scores["screener_roll"] == pytest.approx(1.0)
    assert b.scores["post"] > g.scores["post"]
    assert g.scores["shooter"] > b.scores["shooter"]
    assert set(g.scores) == set(ROLES)
    assert all(0 <= v <= 1 for pr in scores.values() for v in pr.scores.values())


def test_attrs_match_and_miss():
    scores = compute_role_scores([_guard(1), _big(2)])
    assert scores[1].matched_attrs("ball_handler") == ["볼 운반", "픽앤롤 핸들러", "가드 포지션", "패스"]
    assert scores[2].missing_attrs("ball_handler") == ["볼 운반"]  # 가장 큰 항(볼 운반) 0
    assert scores[2].missing_attrs("post") == []


def test_height_is_percentile_within_attendees():
    inputs = [RoleInput(player_id=i, height_cm=h) for i, h in enumerate([170, 175, 175, 190], start=1)]
    s = compute_role_scores(inputs)
    assert [s[i].terms["height"] for i in (1, 2, 3, 4)] == [0.0, pytest.approx(0.5), pytest.approx(0.5), 1.0]


def test_same_input_same_scores():
    a = compute_role_scores([_guard(1), _big(2)])
    b = compute_role_scores([_guard(1), _big(2)])
    assert {k: v.scores for k, v in a.items()} == {k: v.scores for k, v in b.items()}


# ---------------------------------------------------------------------------
# T4 설문 없는 게스트
# ---------------------------------------------------------------------------


def test_guest_without_survey_uses_attendee_mean():
    guest = RoleInput(player_id=9, height_cm=192, positions=frozenset({"PF"}), is_guest=True)
    s = compute_role_scores([_guard(1), _big(2), guest])
    g = s[9]
    # 설문 항은 두 사람 평균
    assert g.terms["handle"] == pytest.approx(0.5)
    assert g.terms["B1:PNR_HANDLER"] == pytest.approx(0.5)
    # 키·포지션은 자기 값 (192 는 공동 최장신)
    assert g.terms["height"] == pytest.approx(0.75)
    assert g.terms["pos:CF"] == 1.0 and g.terms["pos:G"] == 0.0
    # 평균으로 채운 항은 충족 속성으로 말하지 않고, 미충족에는 설문 없음 표시
    assert g.matched_attrs("post") == ["키", "빅맨·포워드 포지션"]
    assert g.missing_attrs("post") == [NO_SURVEY_GUEST]
    assert g.missing_attrs("ball_handler") == [NO_SURVEY_GUEST]


def test_member_without_survey_is_labelled_plainly():
    s = compute_role_scores([_guard(1), RoleInput(player_id=5, height_cm=180)])
    assert s[5].missing_attrs("shooter") == [NO_SURVEY]


def test_nobody_surveyed_still_scores():
    s = compute_role_scores([RoleInput(player_id=i, height_cm=170 + i) for i in range(1, 7)])
    assert s[6].scores["post"] > s[1].scores["post"]  # 키만으로 갈린다


def test_every_term_has_a_label():
    s = compute_role_scores([_guard(1)])
    assert set(s[1].terms) <= set(TERM_LABEL) | {f"B1:{c}" for c in ("PULLUP", "PUTBACK")}


# ---------------------------------------------------------------------------
# T3 슬롯 최적 배치: DP == 완전 탐색
# ---------------------------------------------------------------------------


def _random_roster(n: int, seed: int) -> list[PlayerRoles]:
    rng = random.Random(seed)
    return [
        PlayerRoles(player_id=100 + i, scores={r: round(rng.random(), 3) for r in ROLES}, terms={})
        for i in range(n)
    ]


def _brute(slot_roles, roster) -> float:
    return max(
        sum(p.scores[r] for p, r in zip(perm, slot_roles, strict=True))
        for perm in itertools.permutations(roster, 5)
    )


@pytest.mark.parametrize("n", [5, 6, 7, 8, 9, 10])
@pytest.mark.parametrize("seed", range(4))
def test_dp_matches_brute_force(n, seed):
    roster = _random_roster(n, seed * 31 + n)
    slot_roles = random.Random(seed).choices(ROLES, k=5)
    total, seat = best_lineup(slot_roles, roster)
    assert total == pytest.approx(_brute(slot_roles, roster))
    assert len(set(seat)) == 5
    by_id = {p.player_id: p for p in roster}
    assert sum(by_id[pid].scores[r] for pid, r in zip(seat, slot_roles, strict=True)) == pytest.approx(total)


def test_fewer_than_five_players_is_an_error():
    with pytest.raises(ValueError, match="5명 이상"):
        best_lineup(list(ROLES[:5]), _random_roster(4, 0))


def test_fit_and_bench_alternates():
    play = Play.model_validate(_pnr())
    roster = list(compute_role_scores([
        _guard(1), _big(2), _guard(3), _big(4),
        RoleInput(player_id=5, height_cm=180, positions=frozenset({"SF"}), has_survey=True,
                  b1=frozenset({"CATCH_SHOOT"}), shot_range=1.0, handle=0.33, passing=0.2, stamina=0.9),
        RoleInput(player_id=6, height_cm=178, positions=frozenset({"SG", "SF"}), has_survey=True,
                  b1=frozenset({"CATCH_SHOOT", "OFFBALL_CUT"}), shot_range=0.75, handle=0.33, passing=0.2),
        RoleInput(player_id=7, height_cm=176, is_guest=True),
    ]).values())
    fit = fit_play(play, roster)
    seated = [s.player_id for s in fit.slots]
    assert len(set(seated)) == 5
    assert fit.slots[0].role == "ball_handler" and fit.slots[0].player_id in (1, 3)
    assert fit.slots[4].role == "screener_roll" and fit.slots[4].player_id in (2, 4)
    assert fit.fit == pytest.approx(sum(s.score for s in fit.slots) / 5 * 100, abs=0.05)
    for s in fit.slots:  # 교체 후보는 벤치에서, 그 슬롯에서 가장 높은 사람
        bench = [p for p in roster if p.player_id not in seated]
        assert s.alt_player_id not in seated
        assert s.alt_score == max(p.scores[s.role] for p in bench)


def test_no_alternates_when_exactly_five():
    play = Play.model_validate(_pnr())
    fit = fit_play(play, _random_roster(5, 1))
    assert all(s.alt_player_id is None for s in fit.slots)


def test_rank_filters_by_defense_and_sorts():
    man = Play.model_validate(_pnr())
    zone = Play.model_validate(_pnr(key="zone_test", defense="zone", roles=["post"] * 5))
    anyd = Play.model_validate(_pnr(key="any_test", defense="any", roles=["spacer"] * 5))
    roster = _random_roster(8, 3)
    assert {f.play.key for f in rank_plays([man, zone, anyd], roster, zone=False)} == {"test_pnr", "any_test"}
    assert {f.play.key for f in rank_plays([man, zone, anyd], roster, zone=True)} == {"zone_test", "any_test"}
    ranked = rank_plays([man, zone, anyd], roster, zone=False)
    assert ranked[0].fit >= ranked[1].fit


def test_sixteen_evaluations_are_fast():
    import time

    plays = [Play.model_validate(_pnr(key=f"p{i}", roles=random.Random(i).choices(ROLES, k=5))) for i in range(8)]
    rosters = [_random_roster(10, 1), _random_roster(10, 2)]
    t = time.perf_counter()
    for r in rosters:
        rank_plays(plays, r, top=8)
    assert time.perf_counter() - t < 0.1


def test_inbound_plays_are_not_ranked():
    """인바운드는 상황 전용 — 오늘 추천 순위에 넣지 않는다."""
    half = Play.model_validate(_pnr(key="half"))
    raw = _pnr(key="inb", defense="any", situation="inbound")
    raw["start"][0] = {"x": 0.62, "y": -0.05}  # 공을 넣는 사람은 베이스라인 뒤
    inb = Play.model_validate(raw)
    assert [f.play.key for f in rank_plays([inb, half], _random_roster(8, 1), top=5)] == ["half"]


def test_render_counter_names_and_particles():
    from app.tactics.play import render_counter

    t = "{5}의 롤이 막히면 {3}이 바로, {1}은 윙에서, {2}와는"
    assert render_counter(t) == "5번의 롤이 막히면 3번이 바로, 1번은 윙에서, 2번과는"
    names = ["허재", "서장훈", "허재", "현주엽", "서장훈"]
    assert render_counter(t, names) == "서장훈의 롤이 막히면 허재가 바로, 허재는 윙에서, 서장훈과는"
