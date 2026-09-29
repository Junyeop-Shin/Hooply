import { describe, expect, it } from 'vitest'
import type { Play } from '../api/types'
import { RIM, frameAt, shownStep, stepStates, zigzag } from './tactics'

const P = (x: number, y: number) => ({ x, y })

/** 하이 픽앤롤 축소판: 스크린 → 드리블·롤 → 패스 → 슛 */
const play: Play = {
  key: 'test', name: '테스트', summary: '', defense: 'man', situation: 'half_court', counter: '', opp_defense: 'man', screen_call: 'stay',
  start: [P(0.5, 0.66), P(0.95, 0.05), P(0.05, 0.05), P(0.15, 0.48), P(0.66, 0.42)],
  ball: 1,
  roles: ['ball_handler', 'shooter', 'shooter', 'spacer', 'screener_roll'],
  steps: [
    { caption: '스크린', actions: [{ type: 'screen', slot: 5, to: P(0.57, 0.63), target: 1 }] },
    { caption: '돌파·롤', actions: [{ type: 'dribble', slot: 1, to: P(0.72, 0.4), target: null }, { type: 'cut', slot: 5, to: P(0.52, 0.13), target: null }] },
    { caption: '패스', actions: [{ type: 'pass', slot: 1, to: null, target: 5 }] },
    { caption: '슛', actions: [{ type: 'shot', slot: 5, to: null, target: null }] },
  ],
}

describe('stepStates', () => {
  it('단계마다 위치와 공 가진 슬롯이 바뀐다', () => {
    const s = stepStates(play)
    expect(s).toHaveLength(5)
    expect(s.map((x) => x.holder)).toEqual([1, 1, 1, 5, null])
    expect(s[1].pos[4]).toEqual(P(0.57, 0.63))
    expect(s[2].pos[0]).toEqual(P(0.72, 0.4))
    expect(s[0].pos[4]).toEqual(P(0.66, 0.42)) // 시작 위치는 건드리지 않는다
  })
})

describe('frameAt', () => {
  const s = stepStates(play)

  it('정수 위치에서는 그 단계가 끝난 상태와 같다', () => {
    expect(frameAt(play, s, 2).pos).toEqual(s[2].pos)
    expect(frameAt(play, s, 0).ball).toEqual(s[0].pos[0])
  })

  it('패스 단계 중간에는 공이 두 사람 사이를 날아간다', () => {
    const f = frameAt(play, s, 2.5)
    expect(f.ballOffset).toBe(1)
    const a = s[2].pos[0], b = s[2].pos[4]
    expect(f.ball.x).toBeCloseTo((a.x + b.x) / 2, 5)
  })

  it('패스가 끝나면 공은 받은 사람에게, 슛이 끝나면 림에', () => {
    expect(frameAt(play, s, 3).ball).toEqual(s[3].pos[4])
    expect(frameAt(play, s, 4).ball).toEqual(RIM)
    expect(frameAt(play, s, 4).ballOffset).toBe(0)
  })

  it('범위를 벗어난 cursor 는 끝으로 자른다', () => {
    expect(frameAt(play, s, 99).pos).toEqual(s[4].pos)
    expect(frameAt(play, s, -1).pos).toEqual(s[0].pos)
  })
})

describe('shownStep', () => {
  it('멈춰 있으면 다음 단계, 재생 중이면 지금 단계, 끝이면 없음', () => {
    expect(shownStep(play, 0)).toBe(0)
    expect(shownStep(play, 1.4)).toBe(1)
    expect(shownStep(play, 3)).toBe(3)
    expect(shownStep(play, 4)).toBeNull()
  })

  it('재생 위치가 0 아래로 살짝 내려가도 첫 단계를 보여 준다 (음수 단계 번호 방지)', () => {
    expect(shownStep(play, -0.001)).toBe(0)
  })
})

describe('zigzag', () => {
  it('시작점과 끝점을 지난다', () => {
    const d = zigzag(0, 0, 30, 0)
    expect(d.startsWith('M0.00,0.00')).toBe(true)
    expect(d.endsWith('L30.00,0.00')).toBe(true)
  })
})
