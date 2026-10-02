import { describe, expect, it } from 'vitest'
import { isPristineQuarter, lineupSig } from './quarter-draft'

const base = { black: [3, 1, 2, 4, 5], white: [6, 7, 8, 9, 10], home: 1, away: 2 }

describe('isPristineQuarter', () => {
  it('새로 만든 그대로(0:0 · 명단 그대로)면 묻지 않아도 된다', () => {
    expect(isPristineQuarter({ ...base, black_score: 0, white_score: 0, seed: lineupSig(base) })).toBe(true)
  })
  it('명단 순서만 다른 것은 같은 명단이다', () => {
    expect(isPristineQuarter({ ...base, black: [5, 4, 3, 2, 1], black_score: 0, white_score: 0, seed: lineupSig(base) })).toBe(true)
  })
  it('점수를 넣었거나 명단을 바꿨거나 서버 기록이면 묻는다', () => {
    const seed = lineupSig(base)
    expect(isPristineQuarter({ ...base, black_score: 2, white_score: 0, seed })).toBe(false)
    expect(isPristineQuarter({ ...base, black: [1, 2, 3, 4, 11], black_score: 0, white_score: 0, seed })).toBe(false)
    expect(isPristineQuarter({ ...base, home: 3, black_score: 0, white_score: 0, seed })).toBe(false)
    expect(isPristineQuarter({ ...base, black_score: 0, white_score: 0 })).toBe(false)
  })
})
