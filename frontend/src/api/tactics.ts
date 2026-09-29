import { api } from './client'
import type { AiTactics, EventPlayView, PlayCheck, PresetList, RoleSuggestion, TacticComment, TacticRecommendation, TeamPlayIn, TeamPlayView } from './types'

/** 전술 추천 · 전술판 (docs/07 8.3절). play_key 는 "preset:high_pnr" · "team:12"(팀이 만든 전술) 형태 */
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

/** 팀이 직접 만든 전술 (docs/07 FR-57 ~ FR-59) */
export const teamPlaysApi = {
  list: (teamId: number) => api<{ items: TeamPlayView[] }>(`/teams/${teamId}/plays`),
  get: (teamId: number, id: number) => api<TeamPlayView>(`/teams/${teamId}/plays/${id}`),
  create: (teamId: number, body: TeamPlayIn) => api<TeamPlayView>(`/teams/${teamId}/plays`, { method: 'POST', body }),
  update: (teamId: number, id: number, body: TeamPlayIn) => api<TeamPlayView>(`/teams/${teamId}/plays/${id}`, { method: 'PUT', body }),
  remove: (teamId: number, id: number) => api<void>(`/teams/${teamId}/plays/${id}`, { method: 'DELETE' }),
  /** 저장하지 않고 재생 가능성 검사 + 규칙 역할 추출 */
  check: (teamId: number, body: TeamPlayIn) => api<PlayCheck>(`/teams/${teamId}/plays:check`, { method: 'POST', body }),
  /** AI 역할 태깅 (LangChain 체인 D). AI 를 못 쓰면 규칙 결과 */
  aiRoles: (teamId: number, body: TeamPlayIn) => api<RoleSuggestion>(`/teams/${teamId}/plays:ai-roles`, { method: 'POST', body }),
}

/** 전술 댓글 (docs/07 FR-60) — 팀 안에서 전술 하나에 */
export const tacticCommentsApi = {
  list: (teamId: number, playKey: string) => api<{ items: TacticComment[] }>(`/teams/${teamId}/tactics/${encodeURIComponent(playKey)}/comments`),
  add: (teamId: number, playKey: string, body: string) =>
    api<TacticComment>(`/teams/${teamId}/tactics/${encodeURIComponent(playKey)}/comments`, { method: 'POST', body: { body } }),
  remove: (teamId: number, id: number) => api<void>(`/teams/${teamId}/tactic-comments/${id}`, { method: 'DELETE' }),
}
