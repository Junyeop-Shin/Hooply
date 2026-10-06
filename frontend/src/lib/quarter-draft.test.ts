import { describe, expect, it } from 'vitest'
import { draftMatchesServer, isPristineQuarter, lineupSig } from './quarter-draft'

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

describe('draftMatchesServer', () => {
  const server = [
    { quarter_no: 1, black_score: 10, white_score: 8, duration_min: 8, black: [1, 2, 3, 4, 5], white: [6, 7, 8, 9, 10], home: 1, away: 2 },
    { quarter_no: 2, black_score: 7, white_score: 12, duration_min: 8, black: [1, 2, 3, 4, 11], white: [6, 7, 8, 9, 10], home: 1, away: 2 },
  ]
  it('서버 기록을 그대로 옮겨 온 초안은 같다 (명단 순서는 무시)', () => {
    expect(draftMatchesServer(server, server)).toBe(true)
    expect(draftMatchesServer([{ ...server[0], black: [5, 4, 3, 2, 1] }, server[1]], server)).toBe(true)
  })
  it('점수 · 길이 · 명단 · 쿼터 수가 하나라도 다르면 고친 것이다', () => {
    expect(draftMatchesServer([{ ...server[0], black_score: 11 }, server[1]], server)).toBe(false)
    expect(draftMatchesServer([{ ...server[0], duration_min: 10 }, server[1]], server)).toBe(false)
    expect(draftMatchesServer([server[0], { ...server[1], white: [6, 7, 8, 9, 12] }], server)).toBe(false)
    expect(draftMatchesServer([server[0]], server)).toBe(false)
  })
  it('서버 기록이 없으면 미리 만든 빈 쿼터만 있을 때 "안 고친" 것이다', () => {
    const seed = lineupSig(base)
    expect(draftMatchesServer([{ ...base, quarter_no: 1, black_score: 0, white_score: 0, duration_min: 8, seed }], [])).toBe(true)
    expect(draftMatchesServer([{ ...base, quarter_no: 1, black_score: 3, white_score: 0, duration_min: 8, seed }], [])).toBe(false)
    expect(draftMatchesServer([{ ...base, quarter_no: 1, black_score: 0, white_score: 0, duration_min: 8 }], [])).toBe(false)
  })
})
