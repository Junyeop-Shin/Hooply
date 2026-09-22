"""설계서 13.4절: 실력 모델 시뮬레이션을 회귀 테스트로 유지한다 (scripts/simulate_rating.py).

핵심 주장 두 가지가 무너지면 실패한다.
  1) 잔차 기반 모델(잔차 Elo · RAPM)이 원시 코트 마진 누적보다 참값 순위를 뚜렷이 더 잘 복원한다.
  2) 팀 균형이 좋아질수록 원시 마진은 쓸모를 잃지만(자기 파괴적 되먹임), 잔차 모델은 훨씬 덜 무너진다.
반복 수를 줄여 빠르게 돌리므로 수치는 스크립트 기본값보다 흔들린다 — 차이의 방향과 크기만 본다.
"""

from scripts.simulate_rating import run


def test_residual_models_beat_raw_margin_under_app_conditions():
    # 앱의 실제 조건: 추정치로 팀을 균형 맞추고, 설문 사전값(ρ≈0.65)이 있다
    res = run(reps=8, seed=1, survey_rho=0.65, balance="estimate", checkpoints=(160, 320))
    r160, r320 = res[160], res[320]
    assert r320["elo"] > r320["raw_total"] + 0.15, res
    assert r320["rapm"] > r320["raw_total"] + 0.15, res
    assert r320["elo"] > 0.75 and r320["rapm"] > 0.75, res
    assert r320["raw_total"] < 0.75, res
    # 역선택: 잘하는 사람일수록 강한 상대를 만난다 → 마진만 보면 과소평가된다
    assert r320["adverse"] > 0.2, res
    # 잔차 모델은 표본이 늘면 좋아진다
    assert r320["elo"] >= r160["elo"] - 0.05, res


def test_raw_margin_collapses_when_teams_are_perfectly_balanced():
    # 배정이 완벽히 성공한 극한: 원시 마진은 거의 노이즈, 잔차 모델(특히 RAPM)은 신호를 건진다
    res = run(reps=8, seed=2, survey_rho=None, balance="true", checkpoints=(320,))[320]
    assert res["raw_total"] < 0.4, res
    assert res["rapm"] > res["raw_total"] + 0.25, res
    assert res["elo"] > res["raw_total"], res
