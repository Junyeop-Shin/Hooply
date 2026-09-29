import { describe, expect, it } from 'vitest'
import { isPaint, isThree, rimDistance, zoneOf } from './court'

/** 백엔드 tests/test_tactics.py 의 T1 과 같은 점 — 두 구현이 같은 답을 내야 한다 */
describe('zoneOf (docs/07 8.1)', () => {
  it.each([
    [0.06, 0.1, 'three'],
    [0.94, 0.1, 'three'],
    [0.5, 0.6, 'three'],
    [0.5, 0.55, 'mid'],
    [0.5, 0.3, 'paint'],
    [0.5, 0.0, 'paint'],
    [0.07, 0.1, 'mid'],
  ] as const)('(%s, %s) → %s', (x, y, zone) => {
    expect(zoneOf(x, y)).toBe(zone)
  })

  it('탑 3점 위치의 림 거리는 약 6.83m', () => {
    expect(rimDistance(0.5, 0.6)).toBeCloseTo(6.825, 3)
  })

  it('베이스라인 바로 위 코너 직선 안쪽은 림 거리가 6.75m 를 넘어도 2점', () => {
    const x = (7.5 - 6.58) / 15
    expect(rimDistance(x, 0)).toBeGreaterThan(6.75)
    expect(isThree(x, 0)).toBe(false)
  })

  it('페인트존 모서리는 선 위를 포함한다', () => {
    expect(isPaint((7.5 + 2.45) / 15, 5.8 / 14)).toBe(true)
    expect(isPaint((7.5 + 2.5) / 15, 0.2)).toBe(false)
  })
})
