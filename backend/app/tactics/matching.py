"""슬롯 최적 배치와 전술 순위 (docs/07 FR-44, FR-45).

한 팀(블랙 또는 화이트)의 선수 n명 중 5명을 골라 전술의 슬롯 5개에 앉혀, 슬롯 역할 점수의 합이 가장
크게 한다. 선수를 한 명씩 보면서 "이미 채운 슬롯 집합(5비트)"만 상태로 들고 가는 DP 라서 계산량이
n × 32 × 5 다. 10명이어도 1,600번이고, 전술 14개 × 두 팀이어도 몇 ms 안쪽이다.

적합도 = 앉힌 5명의 역할 점수 평균 × 100 (0~100).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.tactics.play import Defense, Play, Role
from app.tactics.roles import PlayerRoles

SLOTS = 5
FULL = (1 << SLOTS) - 1
_NEG = float("-inf")
_TIE = 1e-9  # 점수 비교 허용 오차. 같으면 먼저 본 선수(명단 순서)를 남긴다


@dataclass(frozen=True)
class SlotPick:
    slot: int  # 1~5
    role: Role
    player_id: int
    score: float  # 0~1
    alt_player_id: int | None  # 교체 후보: 이 슬롯에 앉혔을 때 점수가 가장 높은 벤치 선수 (벤치가 없으면 None)
    alt_score: float | None


@dataclass(frozen=True)
class PlayFit:
    play: Play
    fit: float  # 0~100, 소수 첫째 자리
    slots: tuple[SlotPick, ...]


def best_lineup(slot_roles: Sequence[Role], roster: Sequence[PlayerRoles]) -> tuple[float, list[int]]:
    """슬롯 역할 5개와 선수 명단 → (점수 합, 슬롯 순서대로의 player_id 5개).

    dp[mask] = 지금까지 본 선수들로 mask 의 슬롯을 채웠을 때의 최대 점수. 선수마다 "안 앉힌다" 또는
    "빈 슬롯 하나에 앉힌다"를 고른다. 되짚기용으로 (이전 mask, 앉힌 슬롯) 을 선수 단계마다 남긴다.
    """
    if len(slot_roles) != SLOTS:
        raise ValueError("슬롯은 5개여야 해요")
    if len(roster) < SLOTS:
        raise ValueError(f"선수가 {SLOTS}명 이상이어야 해요 (현재 {len(roster)}명)")
    dp = [_NEG] * (FULL + 1)
    dp[0] = 0.0
    back: list[list[tuple[int, int] | None]] = []  # back[k][mask] = (이전 mask, 슬롯 or -1)
    for pr in roster:
        s = [pr.scores[r] for r in slot_roles]
        new = dp[:]  # 이 선수를 앉히지 않는 경우
        step: list[tuple[int, int] | None] = [(m, -1) if dp[m] > _NEG else None for m in range(FULL + 1)]
        for mask in range(FULL + 1):
            if dp[mask] == _NEG:
                continue
            for k in range(SLOTS):
                if mask >> k & 1:
                    continue
                nm = mask | 1 << k
                v = dp[mask] + s[k]
                if v > new[nm] + _TIE:
                    new[nm] = v
                    step[nm] = (mask, k)
        dp = new
        back.append(step)

    seat = [0] * SLOTS
    mask = FULL
    for idx in range(len(roster) - 1, -1, -1):
        prev = back[idx][mask]
        assert prev is not None
        pmask, k = prev
        if k >= 0:
            seat[k] = roster[idx].player_id
        mask = pmask
    return dp[FULL], seat


def fit_play(play: Play, roster: Sequence[PlayerRoles]) -> PlayFit:
    total, seat = best_lineup(play.roles, roster)
    by_id = {p.player_id: p for p in roster}
    bench = [p for p in roster if p.player_id not in seat]
    picks = []
    for k, pid in enumerate(seat):
        role = play.roles[k]
        alt = max(bench, key=lambda p: p.scores[role], default=None)  # 같으면 명단 앞사람
        picks.append(SlotPick(
            slot=k + 1, role=role, player_id=pid, score=by_id[pid].scores[role],
            alt_player_id=alt.player_id if alt else None,
            alt_score=alt.scores[role] if alt else None,
        ))
    return PlayFit(play=play, fit=round(total / SLOTS * 100, 1), slots=tuple(picks))


def allowed_defenses(zone: bool) -> frozenset[Defense]:
    """매니저 토글 "상대가 지역 수비를 써요" → 후보로 삼을 전술의 대상 수비."""
    return frozenset({"zone", "any"}) if zone else frozenset({"man", "any"})


def rank_plays(
    plays: Iterable[Play], roster: Sequence[PlayerRoles], *, zone: bool = False, top: int = 3,
) -> list[PlayFit]:
    """대상 수비가 맞는 전술만 적합도 높은 순으로 `top` 개. 같으면 프리셋 목록 순서."""
    ok = allowed_defenses(zone)
    fits = [fit_play(p, roster) for p in plays if p.defense in ok]
    fits.sort(key=lambda f: -f.fit)  # 안정 정렬이라 동점은 목록 순서 유지
    return fits[:top]
