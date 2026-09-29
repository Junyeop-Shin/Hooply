import { api } from './client'
import type { QuarterBulkResult, QuarterIn, QuarterListView } from './types'

export const quartersApi = {
  list: (eventId: number) => api<QuarterListView>(`/events/${eventId}/quarters`),
  /** 그 회차 쿼터 전체를 한 번에 저장 — 있으면 수정, 없으면 생성, 빠지면 삭제(마진 롤백) */
  bulkSave: (eventId: number, quarters: QuarterIn[]) =>
    api<QuarterBulkResult>(`/events/${eventId}/quarters`, { method: 'PUT', body: { quarters } }),
}
