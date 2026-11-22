/** 화면 여러 곳이 같은 형식으로 날짜를 보여 주도록 모아 둔 표시용 헬퍼. */
import type { EventView } from '../api/types'

/** 일정을 "9/20 (일) 10:00~12:00" 형태로 (자정을 넘으면 "22:00~00:30(다음 날)") */
export function fmtEvent(e: EventView) {
  const d = new Date(e.event_date + 'T00:00:00')
  const day = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()]
  const start = e.start_time?.slice(0, 5), end = e.end_time?.slice(0, 5)
  const nextDay = start && end && end < start ? '(다음 날)' : ''  // 22:00~00:30 — 서버도 다음 날로 본다
  const time = start ? ` ${start}${end ? `~${end}${nextDay}` : ''}` : ''
  return `${d.getMonth() + 1}/${d.getDate()} (${day})${time}`
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
