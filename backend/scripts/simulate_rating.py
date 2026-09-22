"""실력 지표 시뮬레이션 — 설계서 9.1절 "코트 마진의 함정" · 9.3절 실험 3 의 근거 (재현 스크립트).

질문: 쿼터 점수 차(코트 마진)를 그냥 누적하면 실력을 잴 수 있는가, 아니면 "기대 마진 대비 잔차" 를 써야 하는가.

방법 (몬테카를로)
  1. 참값이 있는 가상 동호회를 만든다: 등록 30명, 진짜 실력 ~ N(0, 2²) (쿼터당 득실 기여, 점).
  2. 2.5절 운영 프로토콜을 그대로 돌린다: 매회 12~14명 참석 → 두 팀으로 나눠 그날 고정 → 팀당 5명 출전,
     나머지는 로테이션 → 쿼터 7~10개. 팀 나누기는 앱처럼 **현재 추정치** 기준 스네이크 드래프트 (참값은 모른다).
  3. 쿼터 마진 = Σ(블랙 출전 5명 참값) − Σ(화이트 출전 5명 참값) + N(0, 6²), 정수로 반올림.
  4. 같은 쿼터 기록에서 지표 네 가지를 계산해 참값과의 **스피어만 순위 상관** 을 비교한다.
       원시 누적 마진   : 내가 코트에 있을 때 우리 팀 마진의 합
       쿼터당 평균 마진 : 위 값 ÷ 출전 쿼터
       잔차 Elo         : 앱의 rating_service 식 그대로 (기대 마진 대비 잔차, K=0.35/(1+n/20), 마진 ±15 클립)
       능형 RAPM        : 쿼터를 관측치로 한 ridge 회귀, λ 는 교차검증으로 선택 (9.2절 층 2)
  5. 40~60회 반복해 평균낸다. 160·320쿼터 시점에서 비교한다 (실험 3 표).

왜 원시 마진이 안 되는가 (9.1절) — 이 스크립트가 숫자로 보여 주는 세 가지
  · 제로섬: 한 쿼터에 출전한 10명의 마진 합은 항상 0 이다.
  · 자기 파괴적 되먹임: 배정이 좋아질수록 두 팀 실력이 같아져 마진에는 노이즈만 남는다.
  · 역선택: 잘하는 사람일수록 약한 팀에 배정되므로 마진이 오히려 낮게 나온다 → 참값과 "상대 팀 강도" 의 상관을 함께 출력한다.

참고 문헌
  · Rosenbaum, D. (2004). Measuring How NBA Players Help Their Teams Win. — Adjusted Plus-Minus(APM): 동료·상대를 통제한 +/-.
  · Sill, J. (2010). Improved NBA Adjusted +/- Using Regularization and Out-of-Sample Testing. MIT Sloan Sports Analytics Conf. — RAPM(능형 회귀 APM).
  · Hoerl, A. & Kennard, R. (1970). Ridge Regression. Technometrics. — 능형 회귀.
  · Elo, A. (1978). The Rating of Chessplayers, Past and Present. — 기대값 대비 잔차로 갱신하는 온라인 평점.
  잔차 Elo 갱신식은 RAPM 목적함수 ‖y − Xβ‖² 를 한 관측치씩 경사하강으로 푸는 것과 같다 (∂/∂β_i = −2·x_i·잔차).

실행
  cd backend && uv run python -m scripts.simulate_rating            # 기본 50회 반복
  uv run python -m scripts.simulate_rating --reps 20 --seed 3
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import numpy as np

N_PLAYERS = 30
SKILL_SD = 2.0
NOISE_SD = 6.0
ATTEND = (12, 14)
QUARTERS = (7, 10)
ON_COURT = 5
MARGIN_CLIP = 15
K_BASE, K_DECAY_N = 0.35, 20  # rating_service 와 동일
CHECKPOINTS = (80, 160, 240, 320)
LAMBDAS = (1.0, 3.0, 10.0, 30.0, 100.0)


@dataclass
class Log:
    """쿼터 기록: 출전 명단(참가자 index)과 마진. 지표는 전부 이 기록만으로 계산한다."""

    black: list[np.ndarray] = field(default_factory=list)
    white: list[np.ndarray] = field(default_factory=list)
    margin: list[float] = field(default_factory=list)
    opp_strength: dict[int, list[float]] = field(default_factory=dict)  # 역선택 확인용: 내가 뛴 쿼터의 상대 5명 참값 합

    def __len__(self) -> int:
        return len(self.margin)


def snake_split(ids: np.ndarray, estimate: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """현재 추정치 기준 스네이크 드래프트 (앱은 완전 탐색이지만, 균형을 맞춘다는 점은 같다). 동점은 무작위."""
    order = ids[np.lexsort((rng.random(len(ids)), -estimate[ids]))]
    a, b = [], []
    for i, pid in enumerate(order):
        (a if i % 4 in (0, 3) else b).append(pid)
    return np.array(a), np.array(b)


def elo_ratings(log: Log, prior: np.ndarray, upto: int) -> np.ndarray:
    """앱의 잔차 Elo 를 처음부터 재생 (rating_service.recompute_team 과 같은 식, 워밍업 게이트는 뺐다)."""
    r = prior.astype(float).copy()
    n = np.zeros(N_PLAYERS)
    for q in range(upto):
        b, w = log.black[q], log.white[q]
        m = float(np.clip(log.margin[q], -MARGIN_CLIP, MARGIN_CLIP))
        d = m - (r[b].sum() - r[w].sum())
        k_b, k_w = K_BASE / (1 + n[b] / K_DECAY_N), K_BASE / (1 + n[w] / K_DECAY_N)
        r[b] += k_b * d / ON_COURT
        r[w] -= k_w * d / ON_COURT
        n[b] += 1
        n[w] += 1
    return r


def design_matrix(log: Log, upto: int) -> tuple[np.ndarray, np.ndarray]:
    X = np.zeros((upto, N_PLAYERS))
    for q in range(upto):
        X[q, log.black[q]] = 1.0
        X[q, log.white[q]] = -1.0
    y = np.clip(np.array(log.margin[:upto]), -MARGIN_CLIP, MARGIN_CLIP)
    return X, y


def ridge(X: np.ndarray, y: np.ndarray, lam: float, prior: np.ndarray) -> np.ndarray:
    """β̂ = prior + (XᵀX + λI)⁻¹ Xᵀ(y − X·prior)  (9.2절 닫힌 해)."""
    resid = y - X @ prior
    return prior + np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ resid)


def rapm_ratings(log: Log, prior: np.ndarray, upto: int, rng: np.random.Generator) -> np.ndarray:
    """λ 를 5겹 교차검증으로 고른 능형 RAPM."""
    X, y = design_matrix(log, upto)
    folds = np.array_split(rng.permutation(upto), 5)
    best, best_err = LAMBDAS[0], np.inf
    for lam in LAMBDAS:
        err = 0.0
        for f in folds:
            train = np.setdiff1d(np.arange(upto), f)
            beta = ridge(X[train], y[train], lam, prior)
            err += float(((X[f] @ beta - y[f]) ** 2).sum())
        if err < best_err:
            best, best_err = lam, err
    return ridge(X, y, best, prior)


def raw_margins(log: Log, upto: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(누적 마진, 쿼터당 평균, 출전 수)."""
    total, played = np.zeros(N_PLAYERS), np.zeros(N_PLAYERS)
    for q in range(upto):
        total[log.black[q]] += log.margin[q]
        total[log.white[q]] -= log.margin[q]
        played[log.black[q]] += 1
        played[log.white[q]] += 1
    avg = np.divide(total, played, out=np.zeros(N_PLAYERS), where=played > 0)
    return total, avg, played


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    return float(np.corrcoef(ra, rb)[0, 1])


def simulate_once(rng: np.random.Generator, *, survey_rho: float | None, max_quarters: int, balance: str = "estimate") -> tuple[Log, np.ndarray, np.ndarray]:
    """한 시즌. 반환: (기록, 참값, 사전값).

    balance — 팀을 무엇으로 균형 맞추는가. 원시 마진이 얼마나 쓸모 있는지는 이 조건에 달려 있다 (9.1절 되먹임).
      "random"   : 무작위 (앱을 안 쓸 때)
      "estimate" : 그 시점의 잔차 Elo 추정치 (앱이 실제로 하는 것)
      "true"     : 참값 (배정이 완벽히 성공한 극한 — 설계서 실험 3 의 "균형 배정" 조건)
    """
    true = rng.normal(0, SKILL_SD, N_PLAYERS)
    if survey_rho is None:
        prior = np.zeros(N_PLAYERS)
    else:
        # 참값과 상관이 survey_rho 인 설문 사전값 (같은 분산)
        noise = rng.normal(0, SKILL_SD, N_PLAYERS)
        prior = survey_rho * true + np.sqrt(1 - survey_rho**2) * noise
    log = Log()
    estimate = prior.copy()
    while len(log) < max_quarters:
        ids = rng.choice(N_PLAYERS, rng.integers(ATTEND[0], ATTEND[1] + 1), replace=False)
        key = {"random": rng.random(N_PLAYERS), "estimate": estimate, "true": true}[balance]
        black, white = snake_split(ids, key, rng)
        for q in range(rng.integers(QUARTERS[0], QUARTERS[1] + 1)):
            on_b = black[(np.arange(ON_COURT) + q) % len(black)]  # 로테이션: 5명 뛰고 나머지는 쉰다
            on_w = white[(np.arange(ON_COURT) + q) % len(white)]
            margin = float(np.round(true[on_b].sum() - true[on_w].sum() + rng.normal(0, NOISE_SD)))
            log.black.append(on_b)
            log.white.append(on_w)
            log.margin.append(margin)
            for p in on_b:
                log.opp_strength.setdefault(int(p), []).append(float(true[on_w].sum()))
            for p in on_w:
                log.opp_strength.setdefault(int(p), []).append(float(true[on_b].sum()))
        estimate = elo_ratings(log, prior, len(log))  # 다음 회차 배정은 갱신된 추정치로 — 자기 파괴적 되먹임을 그대로 재현
    return log, true, prior


def run(reps: int = 50, seed: int = 0, *, survey_rho: float | None = None, balance: str = "estimate", checkpoints=CHECKPOINTS, min_played: int = 8) -> dict[int, dict[str, float]]:
    """체크포인트별 {지표: 평균 스피어만 상관}. 출전 쿼터가 min_played 미만인 사람은 그 시점 비교에서 뺀다."""
    rng = np.random.default_rng(seed)
    acc: dict[int, dict[str, list[float]]] = {c: {"raw_total": [], "raw_avg": [], "elo": [], "rapm": [], "adverse": []} for c in checkpoints}
    for _ in range(reps):
        log, true, prior = simulate_once(rng, survey_rho=survey_rho, max_quarters=max(checkpoints), balance=balance)
        for c in checkpoints:
            total, avg, played = raw_margins(log, c)
            keep = played >= min_played
            elo = elo_ratings(log, prior, c)
            rapm = rapm_ratings(log, prior, c, rng)
            acc[c]["raw_total"].append(spearman(true[keep], total[keep]))
            acc[c]["raw_avg"].append(spearman(true[keep], avg[keep]))
            acc[c]["elo"].append(spearman(true[keep], elo[keep]))
            acc[c]["rapm"].append(spearman(true[keep], rapm[keep]))
            # 역선택: 참값이 높을수록 더 강한 상대를 만나는가 (양의 상관이면 마진이 실력을 과소평가한다)
            opp = np.array([np.mean(log.opp_strength.get(p, [0.0])[: c]) for p in range(N_PLAYERS)])
            acc[c]["adverse"].append(float(np.corrcoef(true[keep], opp[keep])[0, 1]))
    return {c: {k: float(np.mean(v)) for k, v in d.items()} for c, d in acc.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    arms = (
        ("팀을 무작위로 나눔 · 설문 없음", None, "random"),
        ("추정치로 균형 (앱의 실제 동작) · 설문 없음", None, "estimate"),
        ("추정치로 균형 · 설문 ρ=0.65", 0.65, "estimate"),
        ("참값으로 완벽 균형 (배정이 성공한 극한, 실험 3 조건) · 설문 없음", None, "true"),
    )
    for label, rho, balance in arms:
        res = run(args.reps, args.seed, survey_rho=rho, balance=balance)
        print(f"\n[{label}] 반복 {args.reps}회 · 참값과의 스피어만 순위 상관")
        print(f"{'누적 쿼터':>8} | {'원시 누적 마진':>12} | {'쿼터당 평균':>10} | {'잔차 Elo(앱)':>11} | {'능형 RAPM':>9} | {'역선택(참값↔상대강도)':>18}")
        for c, r in res.items():
            print(f"{c:>8} | {r['raw_total']:>12.2f} | {r['raw_avg']:>10.2f} | {r['elo']:>11.2f} | {r['rapm']:>9.2f} | {r['adverse']:>18.2f}")


if __name__ == "__main__":
    main()
