"""AI 검증 스크립트의 점검·보고서 부분 (네트워크 없이). 실제 실행은 배포된 서버를 부른다 (scripts/eval_llm.py)."""

import httpx

from scripts import eval_llm as ev


def _resp(body: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def test_checks_flag_leftover_alias_outsider_and_leak():
    roster, everyone = {"허재", "서장훈"}, {"허재", "서장훈", "현주엽"}
    a = ev._check_a("9/27", _resp({"summary": "P3가 좋아요", "key_players": ["현주엽 — 슛"], "chemistry": [], "gaps": [],
                                   "watch_point": "", "fallback": False, "cached": False}), 1.0, roster, everyone)
    assert "가명이 남음" in a.problems and any("현주엽" in p for p in a.problems)
    b = ev._check_b("9/27", _resp({"why_position": "허재님은 PG", "role": "등급이 높아요", "partner": "", "fallback": False}), 1.0, roster, everyone)
    assert "실력 정보 누설" in b.problems
    c = ev._check_c("9/27", _resp({"one_liner": "좋아요", "items": [{"play_key": "preset:b", "reason": "x", "key_roles": [], "caution": ""},
                                                                     {"play_key": "preset:a", "reason": "y", "key_roles": ["허재 — 운반"], "caution": ""}],
                                   "fallback": False}), 1.0, ["preset:a", "preset:b"], roster, everyone)
    assert "추천 순서가 바뀜" in c.problems
    fb = ev._check_a("9/27", _resp({"summary": "", "key_players": [], "chemistry": [], "gaps": [], "watch_point": "",
                                    "fallback": True, "fail_reason": "timeout"}), 9.0, roster, everyone)
    assert fb.fallback and fb.problems == []  # 폴백은 점검하지 않는다


def test_report_has_sample_source_and_tables():
    good = ev._check_b("9/27", _resp({"why_position": "허재님은 가장 선호하는 PG", "role": "볼 운반", "partner": "", "fallback": False, "cached": False}),
                       2.0, {"허재"}, {"허재"})
    fb = ev.Call("A", "9/27", True, True, False, "error:X:503", 5.0)
    md = ev.report([good, fb], {"base": "https://x", "team": ev.DEMO_TEAM, "events": ["2026-09-27"], "members_logged_in": 1})
    assert "표본 출처: 데모 팀" in md and "실제 동호회 팀 0건" in md
    assert "error:X:503 1" in md and "B · 팀원용 AI 한마디" in md and "왜 이 포지션" in md
