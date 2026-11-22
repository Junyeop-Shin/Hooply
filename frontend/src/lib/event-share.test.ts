/** 일정 알리기 문구 (docs/10 F-1) — 카카오톡 텍스트 메시지는 200자까지라 그 안에 들어와야 한다. */
import { describe, expect, it } from 'vitest'
import type { EventView } from '../api/types'
import { SHARE_TEXT_MAX, eventShareText } from './event-share'

const ev = (over: Partial<EventView> = {}): EventView => ({
  id: 7, team_id: 1, title: '일요 정기전', event_date: '2026-11-29', start_time: '10:00:00', end_time: '12:00:00',
  venue: '서초 사회체육관', rsvp_deadline: null, status: 'OPEN', rsvp_open: true, ...over,
} as EventView)
const names = (n: number) => Array.from({ length: n }, (_, i) => `선수${i + 1}`)

describe('eventShareText', () => {
  it('아직 아무도 응답하지 않았으면 날짜 · 장소와 응답 요청만 담는다', () => {
    expect(eventShareText(ev(), { attend: 0, responded: 0, pending: names(12) })).toBe(
      '[HOOPLY] 일요 정기전 · 11/29 (일) 10:00~12:00\n서초 사회체육관\n참석 여부를 알려 주세요.',
    )
  })

  it('응답이 들어오면 참석 · 미응답 인원과 아직 응답 안 한 사람의 이름을 적는다', () => {
    expect(eventShareText(ev(), { attend: 9, responded: 9, pending: ['김민수', '박지훈', '이영호'] })).toBe(
      '[HOOPLY] 일요 정기전 · 11/29 (일) 10:00~12:00\n서초 사회체육관\n참석 9명 · 미응답 3명\n아직 응답 안 한 분: 김민수, 박지훈, 이영호\n참석 여부를 알려 주세요.',
    )
  })

  it('응답 마감이 있으면 그때까지 알려 달라고 한다', () => {
    const deadline = new Date(2026, 10, 28, 22, 0).toISOString()  // 기기 시각으로 11/28 밤 10시
    const text = eventShareText(ev({ rsvp_deadline: deadline }), { attend: 0, responded: 0, pending: names(12) })
    expect(text.split('\n').at(-1)).toBe('11/28 오후 10:00까지 참석 여부를 알려 주세요.')
  })

  it('미응답이 10명을 넘으면 이름 없이 사람 수만 적는다', () => {
    const text = eventShareText(ev(), { attend: 5, responded: 6, pending: names(11) })
    expect(text).toContain('참석 5명 · 미응답 11명')
    expect(text).not.toContain('아직 응답 안 한 분')
  })

  it('모두 응답했으면 응답 요청 문구를 뺀다', () => {
    expect(eventShareText(ev(), { attend: 12, responded: 14, pending: [] })).toBe(
      '[HOOPLY] 일요 정기전 · 11/29 (일) 10:00~12:00\n서초 사회체육관\n참석 12명 · 모두 응답했어요',
    )
  })

  it('제목 · 장소가 없으면 날짜로 시작하고 장소 줄을 뺀다', () => {
    expect(eventShareText(ev({ title: null, venue: null }), { attend: 0, responded: 0, pending: names(5) })).toBe(
      '[HOOPLY] 11/29 (일) 10:00~12:00\n참석 여부를 알려 주세요.',
    )
  })

  it('이름을 다 적어 200자를 넘으면 일부만 적지 않고 이름 줄을 통째로 뺀다', () => {
    const long = ev({ venue: '가'.repeat(120) })
    const text = eventShareText(long, { attend: 9, responded: 9, pending: names(10) })
    expect(text.length).toBeLessThanOrEqual(SHARE_TEXT_MAX)
    expect(text).toContain('참석 9명 · 미응답 10명')
    expect(text).not.toContain('아직 응답 안 한 분')
    expect(text).not.toContain('선수1')
  })

  it('제목 · 장소만으로 200자를 넘으면 200자에서 자른다', () => {
    const text = eventShareText(ev({ title: '나'.repeat(100), venue: '가'.repeat(150) }), { attend: 0, responded: 0, pending: [] })
    expect(text.length).toBe(SHARE_TEXT_MAX)
    expect(text.endsWith('…')).toBe(true)
  })
})
