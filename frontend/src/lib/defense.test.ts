import { describe, expect, it } from 'vitest'
import type { Play } from '../api/types'
import { defenseFrameAt, guardSpot, simulateDefense } from './defense'
import { RIM, stepStates } from './tactics'
import { rimDistance } from './court'

const P = (x: number, y: number) => ({ x, y })
// 하이 픽앤롤: 5번이 1번에게 스크린 → 1번 드리블 · 5번 롤 → 패스 → 슛
const pnr: Play = {
  key: 'pnr', name: '픽앤롤', summary: '', defense: 'man', situation: 'half_court', counter: '', opp_defense: 'man', screen_call: 'stay',
  start: [P(0.5, 0.66), P(0.95, 0.05), P(0.05, 0.05), P(0.15, 0.48), P(0.66, 0.42)],
  ball: 1,
  roles: ['ball_handler', 'shooter', 'shooter', 'spacer', 'screener_roll'],
  steps: [
    { caption: '스크린', actions: [{ type: 'screen', slot: 5, to: P(0.57, 0.63), target: 1 }] },
    { caption: '돌파 · 롤', actions: [{ type: 'dribble', slot: 1, to: P(0.7, 0.4), target: null }, { type: 'cut', slot: 5, to: P(0.52, 0.13), target: null }] },
    { caption: '패스', actions: [{ type: 'pass', slot: 1, to: null, target: 5 }] },
    { caption: '슛', actions: [{ type: 'shot', slot: 5, to: null, target: null }] },
  ],
}
const d = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot((a.x - b.x) * 15, (a.y - b.y) * 14)

describe('수비 시뮬레이션', () => {
  it('맨투맨 수비는 자기 사람과 림 사이에 선다', () => {
    const sim = simulateDefense(pnr, stepStates(pnr), { kind: 'man', screen: 'switch' })
    sim.pos[0].forEach((q, i) => {
      expect(rimDistance(q.x, q.y)).toBeLessThan(rimDistance(pnr.start[i].x, pnr.start[i].y))
    })
    // 공을 가진 1번에게 가장 가깝게 붙는다
    const gaps = sim.pos[0].map((q, i) => d(q, pnr.start[i]))
    expect(gaps[0]).toBeLessThan(Math.min(...gaps.slice(1)))
  })

  it('스위치면 스크린 뒤 두 수비가 마크를 맞바꾸고 그대로 간다', () => {
    const sim = simulateDefense(pnr, stepStates(pnr), { kind: 'man', screen: 'switch' })
    expect(sim.guards[0]).toEqual([1, 2, 3, 4, 5])
    expect(sim.guards[1]).toEqual([5, 2, 3, 4, 1]) // x1 → 5번, x5 → 1번
    expect(sim.guards[4]).toEqual([5, 2, 3, 4, 1])
    expect(sim.events[0]).toHaveLength(1)
    expect(sim.notes[0]).toContain('스위치 — 수비 5가 1번, 수비 1이 5번을 막아요')
  })

  it('스테이면 마크가 그대로이고, 걸린 수비는 한 박자 늦게 돌아간다', () => {
    const states = stepStates(pnr)
    const stay = simulateDefense(pnr, states, { kind: 'man', screen: 'stay' })
    expect(stay.guards[1]).toEqual([1, 2, 3, 4, 5])
    expect(stay.notes[0]).toContain('수비 1은 스크린을 돌아 1번을')
    // 단계 중간(0.3)에 x1 은 아직 거의 출발하지 않았다
    const mid = defenseFrameAt(stay, 0.3)
    expect(d(mid[0], stay.pos[0][0])).toBeLessThan(0.05)
    // 끝나면 제자리에 도착
    expect(defenseFrameAt(stay, 1)[0]).toEqual(stay.pos[1][0])
  })

  it('지역 수비는 공에 가장 가까운 수비가 달려 나가고, 나머지는 자리를 지킨다', () => {
    const sim = simulateDefense(pnr, stepStates(pnr), { kind: 'zone', screen: 'switch' })
    const ball = pnr.start[0]
    const closest = Math.min(...sim.pos[0].map((q) => d(q, ball)))
    expect(closest).toBeLessThan(1.2)
    // 슛한 뒤(공 없음)에는 기본 자리 근처로 돌아간다 — 골밑 x5 는 림 가까이
    expect(d(sim.pos[4][4], RIM)).toBeLessThan(2)
  })

  it('모든 수비는 코트 안에 있다 (인바운드 공격수가 코트 밖이어도)', () => {
    const inbound: Play = { ...pnr, start: [P(0.5, -0.05), ...pnr.start.slice(1)] }
    for (const kind of ['man', 'zone'] as const) {
      const sim = simulateDefense(inbound, stepStates(inbound), { kind, screen: 'stay' })
      for (const frame of sim.pos) for (const q of frame) {
        expect(q.x).toBeGreaterThanOrEqual(0); expect(q.x).toBeLessThanOrEqual(1)
        expect(q.y).toBeGreaterThanOrEqual(0); expect(q.y).toBeLessThanOrEqual(1)
      }
    }
  })

  it('슛하는 단계부터 수비는 멈춘다', () => {
    for (const kind of ['man', 'zone'] as const) {
      const sim = simulateDefense(pnr, stepStates(pnr), { kind, screen: 'switch' })
      expect(sim.pos[4]).toEqual(sim.pos[3]) // 4단계 = 슛
      expect(defenseFrameAt(sim, 3.5)).toEqual(sim.pos[3])
    }
  })

  it('공에서 먼 공격수의 수비는 더 처진다 (헬프)', () => {
    const ball = P(0.5, 0.66)
    const near = guardSpot(P(0.6, 0.62), ball, false)
    const far = guardSpot(P(0.95, 0.05), ball, false)
    expect(d(far, P(0.95, 0.05))).toBeGreaterThan(d(near, P(0.6, 0.62)))
  })
})
