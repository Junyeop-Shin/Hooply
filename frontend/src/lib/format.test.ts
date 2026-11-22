import { describe, expect, it } from 'vitest'
import { fmtDeadline } from './format'

/** 기기 시각으로 만든 ISO 문자열 — 테스트를 어느 시간대에서 돌려도 같은 시각으로 읽힌다 */
const local = (h: number, m: number) => new Date(2026, 10, 28, h, m).toISOString()

describe('fmtDeadline', () => {
  it('응답 마감을 "월/일 오전·오후 시:분" 으로 적는다', () => {
    expect(fmtDeadline(local(22, 0))).toBe('11/28 오후 10:00')
    expect(fmtDeadline(local(9, 5))).toBe('11/28 오전 9:05')
  })

  it('자정은 오전 12시, 정오는 오후 12시', () => {
    expect(fmtDeadline(local(0, 5))).toBe('11/28 오전 12:05')
    expect(fmtDeadline(local(12, 30))).toBe('11/28 오후 12:30')
  })
})
