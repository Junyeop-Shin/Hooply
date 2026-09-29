import { api } from './client'
import type { AiTactics, EventPlayView, PresetList, TacticRecommendation } from './types'

/** 전술 추천 · 전술판 (docs/07 8.3절). play_key 는 "preset:high_pnr" 형태 */
export const tacticsApi = {
  presets: () => api<PresetList>('/tactics/presets'),
  recommend: (eventId: number, zone: boolean) => api<TacticRecommendation>(`/events/${eventId}/tactics/recommend?zone=${zone}`),
  play: (eventId: number, playKey: string) => api<EventPlayView>(`/events/${eventId}/tactics/${encodeURIComponent(playKey)}`),
  /** AI 전술 추천 설명 (LangChain 체인 C) — 한 팀. 같은 팀·같은 수비 보기면 서버가 저장해 둔 결과 */
  aiRecommend: (eventId: number, squadNo: number, zone: boolean) =>
    api<AiTactics>(`/events/${eventId}/tactics/ai-recommend?squad_no=${squadNo}&zone=${zone}`, { method: 'POST' }),
  /** 매니저가 자리를 바꿔 저장. 빈 slots 는 추천 배치로 되돌리기 */
  saveSlots: (eventId: number, playKey: string, body: { squad_no: number; slots: { slot: number; player_id: number }[] }) =>
    api<EventPlayView>(`/events/${eventId}/tactics/${encodeURIComponent(playKey)}/slots`, { method: 'PUT', body }),
}
