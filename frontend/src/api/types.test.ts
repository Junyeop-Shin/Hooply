import { describe, expect, it } from 'vitest'
import { localISODate, reasonLabel } from './types'

describe('localISODate', () => {
  it('기기 로컬 날짜를 YYYY-MM-DD 로 만든다 (UTC 가 아니라)', () => {
    // 로컬 자정 직후: toISOString 은 전날(UTC)이 될 수 있지만 localISODate 는 오늘이어야 한다
    const d = new Date(2026, 8, 9, 0, 30) // 2026-09-09 00:30 로컬
    expect(localISODate(d)).toBe('2026-09-09')
    expect(localISODate(new Date(2026, 0, 1))).toBe('2026-01-01')
  })
})

describe('reasonLabel', () => {
  it('우리 팀 후보에는 기본 문구, 상대 팀 후보에는 상대 맥락 문구를 쓴다', () => {
    expect(reasonLabel('PASS', true)).toBe('패스가 좋았어요')
    expect(reasonLabel('PASS', false)).toBe('패스가 인상적이었어요')
    expect(reasonLabel('TEMPO', false)).toBe('같이 하고 싶어요')
    expect(reasonLabel('OTHER', null)).toBe('기타')
  })
})
