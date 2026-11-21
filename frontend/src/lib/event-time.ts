/** 일정 폼의 시각 계산 — 자정을 넘는 일정(22:00~00:30)과 지난 일정 채우기 (docs/09 2-10 · 2-13). */

/** "20:00" → 1200(분). 값이 없거나 형식이 다르면 null */
export function toMinutes(hhmm: string): number | null {
  const [h, m] = (hhmm ?? '').split(':').map(Number)
  return Number.isNaN(h) || Number.isNaN(m) ? null : h * 60 + m
}

/** "20:00" 에 분을 더한다. 자정을 넘으면 24시간으로 감는다 — 종료가 시작보다 이르면 서버가 다음 날로 본다 (docs/09 2-13) */
export function addMinutes(hhmm: string, minutes: number): string {
  const base = toMinutes(hhmm)
  if (base === null) return hhmm
  const total = (base + minutes) % (24 * 60)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

/** 시작~종료 길이(분). 종료가 시작보다 이르면 다음 날 끝나는 것으로 센다. 같거나 값이 없으면 null */
export function spanMinutes(start: string, end: string): number | null {
  const s = toMinutes(start), e = toMinutes(end)
  if (s === null || e === null || s === e) return null
  return (e - s + 24 * 60) % (24 * 60)
}

/** 종료가 시작보다 이르면 다음 날 끝나는 일정 (22:00~00:30) */
export function endsNextDay(start: string, end: string): boolean {
  const s = toMinutes(start), e = toMinutes(end)
  return s !== null && e !== null && e < s
}

/** 지난 일정을 같은 요일로 옮길 주 수 — 오늘 이후가 될 때까지 일주일씩 (docs/09 2-10) */
export function weeksUntilUpcoming(lastDate: string, today: string): number {
  const base = new Date(lastDate + 'T00:00:00').getTime()
  const t = new Date(today + 'T00:00:00').getTime()
  return Math.max(1, Math.ceil((t - base) / (7 * 86_400_000)))
}
