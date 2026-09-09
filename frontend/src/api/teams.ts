import { api } from './client'
import type { LeaderboardEntry, LeaderboardMetric, MergeCandidate, PlayerCard, PlayerCardDetailed, TeamDetail, TeamRole } from './types'

export const teamsApi = {
  create: (input: { name: string; description?: string; home_court?: string }) =>
    api<{ id: number; team_code: string }>('/teams', { method: 'POST', body: input }),
  join: (team_code: string) => api<TeamDetail>('/teams/join', { method: 'POST', body: { team_code } }),
  get: (teamId: number) => api<TeamDetail>(`/teams/${teamId}`),
  update: (teamId: number, patch: { name?: string; description?: string; home_court?: string }) =>
    api<TeamDetail>(`/teams/${teamId}`, { method: 'PATCH', body: patch }),
  regenerateCode: (teamId: number) =>
    api<{ team_code: string }>(`/teams/${teamId}/code:regenerate`, { method: 'POST' }),
  players: (teamId: number, sort: 'name' | 'skill' = 'name') =>
    api<{ items: (PlayerCard | PlayerCardDetailed)[] }>(`/teams/${teamId}/players?sort=${sort}`),
  setRole: (teamId: number, playerId: number, role: TeamRole) =>
    api<PlayerCard>(`/teams/${teamId}/players/${playerId}/role`, { method: 'PATCH', body: { role } }),
  remove: (teamId: number, playerId: number) =>
    api<void>(`/teams/${teamId}/players/${playerId}`, { method: 'DELETE' }),

  leaderboard: (teamId: number, metric: LeaderboardMetric, period?: string) =>
    api<{ items: LeaderboardEntry[] }>(`/teams/${teamId}/stats/leaderboard?metric=${metric}${period ? `&period=${period}` : ''}`),

  // 게스트 레코드 (회차와 무관)
  guests: (teamId: number, q?: string) =>
    api<{ items: PlayerCard[] }>(`/teams/${teamId}/guests${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  mergeCandidates: (teamId: number) => api<{ items: MergeCandidate[] }>(`/teams/${teamId}/guests/merge-candidates`),
  mergeGuest: (guestPlayerId: number, intoPlayerId: number) =>
    api<PlayerCard>(`/players/${guestPlayerId}:merge`, { method: 'POST', body: { into_player_id: intoPlayerId } }),
  unmergeGuest: (playerId: number) => api<PlayerCard>(`/players/${playerId}:unmerge`, { method: 'POST' }),
}
