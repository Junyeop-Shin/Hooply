import { describe, expect, it } from 'vitest'
import { dateParts, fmtDeadline, fmtEvent, fmtTime } from './format'
import type { EventView } from '../api/types'

const ev = (start: string | null, end: string | null) => ({ event_date: '2026-11-29', start_time: start, end_time: end } as EventView)

// B안의 큰 날짜 표기 (docs/11 규칙 2 · 7) — 화면에는 "11.29 SUN", 스크린리더에는 한글
describe('dateParts', () => {
  it('날짜를 "월.일(두 자리)" 과 요일 세 글자로 나누고, 읽어 줄 한글을 함께 준다', () => {
    expect(dateParts('2026-11-29')).toEqual({ md: '11.29', dow: 'SUN', ko: '11월 29일 일요일' })
    expect(dateParts('2026-12-06')).toEqual({ md: '12.06', dow: 'SUN', ko: '12월 6일 일요일' })
    expect(dateParts('2026-11-25')).toEqual({ md: '11.25', dow: 'WED', ko: '11월 25일 수요일' })
  })
})

describe('fmtTime', () => {
  it('시작~종료를 적고, 자정을 넘으면 다음 날이라고 붙인다', () => {
    expect(fmtTime(ev('10:00:00', '12:00:00'))).toBe('10:00~12:00')
    expect(fmtTime(ev('22:00:00', '00:30:00'))).toBe('22:00~00:30(다음 날)')
    expect(fmtTime(ev('20:00:00', null))).toBe('20:00')
    expect(fmtTime(ev(null, null))).toBe('')
  })

  it('fmtEvent 는 같은 시각 표기를 날짜 뒤에 붙인다', () => {
    expect(fmtEvent(ev('10:00:00', '12:00:00'))).toBe('11/29 (일) 10:00~12:00')
    expect(fmtEvent(ev(null, null))).toBe('11/29 (일)')
  })
})

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
