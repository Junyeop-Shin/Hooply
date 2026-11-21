import { describe, expect, it } from 'vitest'
import { addMinutes, endsNextDay, spanMinutes, weeksUntilUpcoming } from './event-time'
import { fmtEvent } from './format'
import type { EventView } from '../api/types'

describe('자정을 넘는 일정 (docs/09 2-13)', () => {
  it('시작을 바꾸면 종료가 24시간으로 감겨 길이를 지킨다', () => {
    expect(addMinutes('22:00', 150)).toBe('00:30')
    expect(addMinutes('20:00', 120)).toBe('22:00')
  })
  it('종료가 시작보다 이르면 다음 날까지의 길이', () => {
    expect(spanMinutes('22:00', '00:30')).toBe(150)
    expect(spanMinutes('10:00', '12:00')).toBe(120)
    expect(spanMinutes('10:00', '10:00')).toBeNull()
    expect(endsNextDay('22:00', '00:30')).toBe(true)
    expect(endsNextDay('10:00', '12:00')).toBe(false)
  })
  it('일정 표시에 "(다음 날)"', () => {
    const e = { event_date: '2026-11-21', start_time: '22:00:00', end_time: '00:30:00' } as EventView
    expect(fmtEvent(e)).toBe('11/21 (토) 22:00~00:30(다음 날)')
  })
})

describe('지난 일정과 같게 채우기 (docs/09 2-10)', () => {
  it('오늘 이후가 될 때까지 일주일씩 뒤로', () => {
    expect(weeksUntilUpcoming('2026-11-15', '2026-11-20')).toBe(1)  // 지난주 일요일 → 이번 주 일요일
    expect(weeksUntilUpcoming('2026-11-01', '2026-11-20')).toBe(3)  // 두 주 쉬었으면 11/22
    expect(weeksUntilUpcoming('2026-11-13', '2026-11-20')).toBe(1)  // 딱 일주일 전 → 오늘
    expect(weeksUntilUpcoming('2026-11-27', '2026-11-20')).toBe(1)  // 다음 주 일정이 이미 있으면 그 다음 주
  })
})
