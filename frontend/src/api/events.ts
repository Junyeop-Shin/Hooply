import { api } from './client'
import type {
  AttendanceList,
  AttendanceStatus,
  AttendanceView,
  EventCreateInput,
  EventGuestInput,
  EventGuestUpdate,
  EventView,
  GuestPreset,
  GuestSimilar,
  LockSuggestion,
  Page,
} from './types'

/** 게스트 등록은 201(등록됨) 또는 200(동명이인 확인) 두 가지로 온다 */
export type GuestRegisterResult = { kind: 'registered'; view: AttendanceView } | { kind: 'similar'; similar: GuestSimilar['similar'] }

export const eventsApi = {
  create: (teamId: number, input: EventCreateInput) =>
    api<EventView>(`/teams/${teamId}/events`, { method: 'POST', body: input }),
  list: (teamId: number, params: { status?: string; page?: number; size?: number; from?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.status) q.set('status', params.status)
    if (params.from) q.set('from', params.from)  // 이 날짜(포함) 이후만 — 홈의 다가오는 일정
    if (params.page) q.set('page', String(params.page))
    if (params.size) q.set('size', String(params.size))
    const qs = q.toString()
    return api<Page<EventView>>(`/teams/${teamId}/events${qs ? `?${qs}` : ''}`)
  },
  get: (eventId: number) => api<EventView>(`/events/${eventId}`),
  update: (eventId: number, patch: Partial<EventCreateInput>) =>
    api<EventView>(`/events/${eventId}`, { method: 'PATCH', body: patch }),
  remove: (eventId: number) => api<void>(`/events/${eventId}`, { method: 'DELETE' }),  // 이력 없이 삭제 — 참석·배정·투표도 함께 지워진다
  closeRsvp: (eventId: number) => api<EventView>(`/events/${eventId}/rsvp:close`, { method: 'POST' }),
  respond: (eventId: number, status: AttendanceStatus, note?: string) =>
    api<AttendanceView>(`/events/${eventId}/attendance`, { method: 'PUT', body: { status, note } }),
  setAttendance: (eventId: number, playerId: number, status: AttendanceStatus) =>
    api<AttendanceView>(`/events/${eventId}/attendances/${playerId}`, { method: 'PUT', body: { status } }),
  attendances: (eventId: number) => api<AttendanceList>(`/events/${eventId}/attendances`),

  registerGuest: async (eventId: number, input: EventGuestInput): Promise<GuestRegisterResult> => {
    const res = await api<AttendanceView | GuestSimilar>(`/events/${eventId}/guests`, { method: 'POST', body: input })
    if ('similar' in res) return { kind: 'similar', similar: res.similar }
    return { kind: 'registered', view: res }
  },
  updateGuest: (eventId: number, playerId: number, patch: EventGuestUpdate) =>
    api<AttendanceView>(`/events/${eventId}/guests/${playerId}`, { method: 'PATCH', body: patch }),
  removeGuest: (eventId: number, playerId: number) =>
    api<void>(`/events/${eventId}/guests/${playerId}`, { method: 'DELETE' }),
  presets: (eventId: number) => api<{ items: GuestPreset[] }>(`/events/${eventId}/guests/presets`),
  suggestions: (eventId: number) => api<{ items: LockSuggestion[] }>(`/events/${eventId}/assignment/suggestions`),
}
