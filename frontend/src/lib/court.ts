/**
 * 코트 좌표 판정 (docs/07 FR-40, 8.1절).
 *
 * 전술 좌표는 0~1 로 저장하고, 판정할 때만 FIBA 하프코트 15m × 14m 로 환산한다.
 *   x: 왼쪽 사이드라인 0 → 오른쪽 사이드라인 1
 *   y: 베이스라인 0 → 하프라인 1
 *
 * 백엔드 `backend/app/tactics/court.py` 와 상수·식이 같다. 한쪽을 고치면 다른 쪽도 고친다.
 */

export const COURT_W = 15 // 하프코트 가로 (m)
export const COURT_H = 14 // 베이스라인 → 하프라인 (m)
export const RIM_X = 7.5 // 림 중심
export const RIM_Y = 1.575 // 베이스라인에서 림 중심까지
export const THREE_R = 6.75 // 3점 아크 반지름
export const CORNER_DX = 6.6 // 코너 3점 직선: 림 중심에서 좌우 6.6m
export const CORNER_Y = 2.99 // 코너 직선이 아크와 만나는 높이
export const PAINT_HALF_W = 2.45 // 페인트존 폭의 절반
export const PAINT_H = 5.8 // 베이스라인 → 자유투 라인
const EPS = 1e-9 // 0.06 × 15 같은 부동소수 오차로 경계가 뒤집히지 않게

export type Zone = 'three' | 'mid' | 'paint'

export function toMeters(x: number, y: number): [number, number] {
  return [x * COURT_W, y * COURT_H]
}

/** 림 중심까지 거리 (m) */
export function rimDistance(x: number, y: number): number {
  const [mx, my] = toMeters(x, y)
  return Math.hypot(mx - RIM_X, my - RIM_Y)
}

/** 3점 라인 밖(라인 위 포함)인가. 코너 직선 구간은 좌우 거리만, 그 위는 아크 거리만 본다 */
export function isThree(x: number, y: number): boolean {
  const [mx, my] = toMeters(x, y)
  if (my <= CORNER_Y) return Math.abs(mx - RIM_X) >= CORNER_DX - EPS
  return Math.hypot(mx - RIM_X, my - RIM_Y) >= THREE_R - EPS
}

export function isPaint(x: number, y: number): boolean {
  const [mx, my] = toMeters(x, y)
  return Math.abs(mx - RIM_X) <= PAINT_HALF_W + EPS && my <= PAINT_H + EPS
}

export function zoneOf(x: number, y: number): Zone {
  if (isThree(x, y)) return 'three'
  if (isPaint(x, y)) return 'paint'
  return 'mid'
}
