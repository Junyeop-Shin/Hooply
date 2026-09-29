import { api } from './client'
import type {
  AdoptedAssignment,
  AiExplanation,
  AiMessage,
  AssignmentRunRequest,
  AssignmentRunView,
  CandidateView,
  ConstraintSet,
  RankingView,
  ValidateResult,
} from './types'

export const rankingsApi = {
  latest: (teamId: number) => api<RankingView>(`/teams/${teamId}/rankings/latest`),
  create: (teamId: number, player_ids: number[]) =>
    api<RankingView>(`/teams/${teamId}/rankings`, { method: 'POST', body: { player_ids } }),
  history: (teamId: number) => api<{ items: RankingView[] }>(`/teams/${teamId}/rankings`),
}

export const assignmentsApi = {
  validate: (eventId: number, body: AssignmentRunRequest) =>
    api<ValidateResult>(`/events/${eventId}/assignments:validate`, { method: 'POST', body }),
  run: (eventId: number, body: AssignmentRunRequest) =>
    api<AssignmentRunView>(`/events/${eventId}/assignments`, { method: 'POST', body }),
  runs: (eventId: number) => api<{ items: AssignmentRunView[] }>(`/events/${eventId}/assignments`),
  lastConstraints: (eventId: number) => api<ConstraintSet>(`/events/${eventId}/assignments/last-constraints`),
  getRun: (runId: number) => api<AssignmentRunView>(`/assignments/runs/${runId}`),
  swap: (candidateId: number, a: number, b: number) =>
    api<CandidateView>(`/assignments/candidates/${candidateId}`, { method: 'PATCH', body: { swaps: [{ player_id_a: a, player_id_b: b }] } }),
  move: (candidateId: number, playerId: number, toSquadNo: number) =>
    api<CandidateView>(`/assignments/candidates/${candidateId}`, { method: 'PATCH', body: { moves: [{ player_id: playerId, to_squad_no: toSquadNo }] } }),
  /** 그룹 교환: a 쪽(같은 팀)은 상대 팀으로, b 쪽은 a 팀으로. 한쪽이 비면 일방 이동. 묶음은 서버가 통째로 움직인다 */
  /** a 는 b 의 팀으로, b 는 a 의 팀으로. 한쪽만 보내면 일방 이동 — 3팀이면 toSquadNo 로 옮길 팀을 준다 */
  exchange: (candidateId: number, aIds: number[], bIds: number[], toSquadNo?: number) =>
    api<CandidateView>(`/assignments/candidates/${candidateId}`, { method: 'PATCH', body: { exchanges: [{ a_player_ids: aIds, b_player_ids: bIds, to_squad_no: toSquadNo ?? null }] } }),
  reset: (candidateId: number) => api<CandidateView>(`/assignments/candidates/${candidateId}:reset`, { method: 'POST' }),
  adopt: (candidateId: number) => api<CandidateView>(`/assignments/candidates/${candidateId}:adopt`, { method: 'POST' }),
  adopted: (eventId: number) => api<AdoptedAssignment>(`/events/${eventId}/assignment/adopted`),
  /** AI 배정 설명 (매니저용, LangChain 체인 A). 같은 배정이면 서버가 저장해 둔 결과를 준다 */
  aiExplanation: (candidateId: number) => api<AiExplanation>(`/assignments/candidates/${candidateId}/ai-explanation`, { method: 'POST' }),
  /** AI 한마디 (팀원용, 체인 B) — 내 것만 */
  aiMessage: (eventId: number) => api<AiMessage>(`/events/${eventId}/assignment/adopted/ai-message`),
}
