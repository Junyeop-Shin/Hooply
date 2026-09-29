import { api } from './client'
import type { EventPlayView, PresetList, SavedPlays, TacticRecommendation } from './types'

/** 전술 추천 · 전술판 · 이름표 (docs/07 8.3절). play_key 는 "preset:high_pnr" 형태 */
export const tacticsApi = {
  presets: () => api<PresetList>('/tactics/presets'),
  saved: (eventId: number) => api<SavedPlays>(`/events/${eventId}/tactics`),
  recommend: (eventId: number, zone: boolean) => api<TacticRecommendation>(`/events/${eventId}/tactics/recommend?zone=${zone}`),
  play: (eventId: number, playKey: string) => api<EventPlayView>(`/events/${eventId}/tactics/${encodeURIComponent(playKey)}`),
  saveSlots: (eventId: number, playKey: string, body: { squad_no: number; slots: { slot: number; player_id: number }[] }) =>
    api<EventPlayView>(`/events/${eventId}/tactics/${encodeURIComponent(playKey)}/slots`, { method: 'PUT', body }),
}
