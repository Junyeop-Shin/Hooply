import { api } from './client'
import type { EventPlayView, PresetList, TacticRecommendation } from './types'

/** 전술 추천 · 전술판 (docs/07 8.3절). play_key 는 "preset:high_pnr" 형태 */
export const tacticsApi = {
  presets: () => api<PresetList>('/tactics/presets'),
  recommend: (eventId: number, zone: boolean) => api<TacticRecommendation>(`/events/${eventId}/tactics/recommend?zone=${zone}`),
  play: (eventId: number, playKey: string) => api<EventPlayView>(`/events/${eventId}/tactics/${encodeURIComponent(playKey)}`),
  /** 매니저가 자리를 바꿔 저장. 빈 slots 는 추천 배치로 되돌리기 */
  saveSlots: (eventId: number, playKey: string, body: { squad_no: number; slots: { slot: number; player_id: number }[] }) =>
    api<EventPlayView>(`/events/${eventId}/tactics/${encodeURIComponent(playKey)}/slots`, { method: 'PUT', body }),
}
