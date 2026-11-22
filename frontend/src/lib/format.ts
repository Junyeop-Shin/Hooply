/** 화면 여러 곳이 같은 형식으로 날짜를 보여 주도록 모아 둔 표시용 헬퍼. */
import type { EventView } from '../api/types'

const WEEK_KO = ['일', '월', '화', '수', '목', '금', '토']
const WEEK_EN = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']

/** 시각을 "10:00~12:00" 으로 (자정을 넘으면 "22:00~00:30(다음 날)", 종료가 없으면 시작만, 시작이 없으면 빈 문자열) */
export function fmtTime(e: Pick<EventView, 'start_time' | 'end_time'>) {
  const start = e.start_time?.slice(0, 5), end = e.end_time?.slice(0, 5)
  if (!start) return ''
  const nextDay = end && end < start ? '(다음 날)' : ''  // 22:00~00:30 — 서버도 다음 날로 본다
  return `${start}${end ? `~${end}${nextDay}` : ''}`
}

/** 일정을 "9/20 (일) 10:00~12:00" 형태로 (자정을 넘으면 "22:00~00:30(다음 날)") */
export function fmtEvent(e: EventView) {
  const d = new Date(e.event_date + 'T00:00:00')
  const time = fmtTime(e)
  return `${d.getMonth() + 1}/${d.getDate()} (${WEEK_KO[d.getDay()]})${time ? ` ${time}` : ''}`
}

/**
 * 큰 날짜 표기의 조각 (docs/11 규칙 2 · 7) — 화면에는 숫자체로 `md`("11.29") 와 `dow`("SUN") 를 보여 주고,
 * 스크린리더에는 `ko`("11월 29일 일요일") 를 읽어 준다
 */
export function dateParts(isoDate: string) {
  const d = new Date(isoDate + 'T00:00:00')
  return {
    md: `${d.getMonth() + 1}.${String(d.getDate()).padStart(2, '0')}`,
    dow: WEEK_EN[d.getDay()],
    ko: `${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEK_KO[d.getDay()]}요일`,
  }
}

/**
 * 응답 마감 시각을 "9/20 오후 10:00" 으로 (기기 시각 기준).
 * 형식이 고정이라 직접 만든다 — 브라우저의 지역 표기(Intl)는 처음 부를 때 느리고 기기마다 표기가 조금씩 다르다
 */
export function fmtDeadline(iso: string) {
  const d = new Date(iso)
  const h = d.getHours()
  return `${d.getMonth() + 1}/${d.getDate()} ${h < 12 ? '오전' : '오후'} ${h % 12 || 12}:${String(d.getMinutes()).padStart(2, '0')}`
}
