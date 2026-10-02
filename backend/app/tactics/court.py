"""코트 좌표 판정 (docs/07 FR-40, 8.1절).

전술 좌표는 0~1 로 저장하고, 판정할 때만 FIBA 하프코트 15m × 14m 로 환산한다.
  x: 왼쪽 사이드라인 0 → 오른쪽 사이드라인 1
  y: 베이스라인 0 → 하프라인 1

프론트 `frontend/src/lib/court.ts` 가 같은 상수·같은 식을 쓴다. 한쪽을 고치면 다른 쪽도 고친다.
"""

import math
from typing import Literal

COURT_W = 15.0  # 하프코트 가로 (m)
COURT_H = 14.0  # 베이스라인 → 하프라인 (m)
RIM_X = 7.5  # 림 중심
RIM_Y = 1.575  # 베이스라인에서 림 중심까지 (1.2m 백보드 + 0.375m)
THREE_R = 6.75  # 3점 아크 반지름 (림 중심 기준)
CORNER_DX = 6.6  # 코너 3점 직선: 림 중심에서 좌우 6.6m (사이드라인 안쪽 0.9m)
CORNER_Y = 2.99  # 코너 직선이 아크와 만나는 높이 = RIM_Y + √(6.75² − 6.6²)
PAINT_HALF_W = 2.45  # 페인트존 폭 4.9m 의 절반
PAINT_H = 5.8  # 베이스라인 → 자유투 라인
_EPS = 1e-9  # 0.06 × 15 같은 부동소수 오차로 경계가 뒤집히지 않게

Zone = Literal["three", "mid", "paint"]


def to_meters(x: float, y: float) -> tuple[float, float]:
    return x * COURT_W, y * COURT_H


def is_three(x: float, y: float) -> bool:
    """3점 라인 밖(라인 위 포함)인가.

    코너 직선 구간(Y ≤ 2.99)은 좌우 거리만, 그 위는 아크 거리만 본다. 명세 8.1의 "또는" 식을 그대로 쓰면
    베이스라인 바로 위 코너 안쪽(좌우 6.55~6.6m)이 아크 거리로 3점이 돼 버려서 구간을 나눴다.
    """
    mx, my = to_meters(x, y)
    if my <= CORNER_Y:
        return abs(mx - RIM_X) >= CORNER_DX - _EPS
    return math.hypot(mx - RIM_X, my - RIM_Y) >= THREE_R - _EPS


def is_paint(x: float, y: float) -> bool:
    mx, my = to_meters(x, y)
    return abs(mx - RIM_X) <= PAINT_HALF_W + _EPS and my <= PAINT_H + _EPS


def zone_of(x: float, y: float) -> Zone:
    if is_three(x, y):
        return "three"
    if is_paint(x, y):
        return "paint"
    return "mid"
