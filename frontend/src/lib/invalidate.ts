/**
 * 일정이 바뀌었을 때 다시 받을 캐시만 고른다. 예전에는 ['events'] 전체를 버려 다른 팀 · 다른 일정까지 다시 받았다.
 *
 * 'events' 로 시작하는 키:
 *   ['events', eventId]                 일정 상세        ┐
 *   ['events', eventId, 'attendances' | 'adopted' | 'quarters' | 'vote' | 'suggestions' | 'guest-presets' | 'validate', …]
 *                                                       ┘ → ['events', eventId] 하나로 함께 무효화된다 (접두어 일치)
 *   ['events', 'team', teamId, …]       팀 일정 목록(일정 탭 · 홈 다가오는 일정 · 지난 일정 불러오기) · 리더보드 기간
 */
import type { QueryClient } from '@tanstack/react-query'

export function invalidateEvent(qc: QueryClient, eventId: number, teamId?: number | null) {
  qc.invalidateQueries({ queryKey: ['events', eventId] })
  // 목록의 참석 수 · 내 응답 · 상태가 바뀐다. 팀을 모르면 모든 팀의 일정 목록(그래도 다른 일정 상세는 건드리지 않는다)
  qc.invalidateQueries({ queryKey: teamId ? ['events', 'team', teamId] : ['events', 'team'] })
}
