/** 화면 여러 곳이 같은 형식으로 날짜를 보여 주도록 모아 둔 표시용 헬퍼. */
import type { EventView } from '../api/types'

/** 일정을 "9/20 (일) 10:00~12:00" 형태로 */
export function fmtEvent(e: EventView) {
  const d = new Date(e.event_date + 'T00:00:00')
  const day = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()]
  const time = e.start_time ? ` ${e.start_time.slice(0, 5)}${e.end_time ? `~${e.end_time.slice(0, 5)}` : ''}` : ''
  return `${d.getMonth() + 1}/${d.getDate()} (${day})${time}`
}
