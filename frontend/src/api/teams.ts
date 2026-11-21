import { api } from './client'
import type { GuestClaimView, LeaderboardEntry, LeaderboardMetric, MergeCandidate, MonthlyMarginView, PlayerCard, PlayerCardDetailed, Position, TeamDetail, TeamRole } from './types'

export const teamsApi = {
  create: (input: { name: string; description?: string; home_court?: string }) =>
    api<{ id: number; team_code: string }>('/teams', { method: 'POST', body: input }),
  join: (team_code: string) => api<TeamDetail>('/teams/join', { method: 'POST', body: { team_code } }),
  get: (teamId: number) => api<TeamDetail>(`/teams/${teamId}`),
  update: (teamId: number, patch: { name?: string; description?: string | null; home_court?: string | null }) =>
    api<TeamDetail>(`/teams/${teamId}`, { method: 'PATCH', body: patch }),
  regenerateCode: (teamId: number) =>
    api<{ team_code: string }>(`/teams/${teamId}/code:regenerate`, { method: 'POST' }),
  players: (teamId: number, sort: 'name' | 'skill' = 'name') =>
    api<{ items: (PlayerCard | PlayerCardDetailed)[] }>(`/teams/${teamId}/players?sort=${sort}`),
  setRole: (teamId: number, playerId: number, role: TeamRole) =>
    api<PlayerCard>(`/teams/${teamId}/players/${playerId}/role`, { method: 'PATCH', body: { role } }),
  leave: (teamId: number) => api<void>(`/teams/${teamId}:leave`, { method: 'POST' }),
  remove: (teamId: number, playerId: number) =>
    api<void>(`/teams/${teamId}/players/${playerId}`, { method: 'DELETE' }),
  /** 매니저가 제외한 회원 — "제외 풀기" 목록 */
  removedPlayers: (teamId: number) => api<{ items: PlayerCard[] }>(`/teams/${teamId}/players?status=REMOVED`),
  /** 한 사람만 제외를 푼다 → 지금 팀 코드로 다시 들어올 수 있다 (코드 재발급과 따로) */
  unremove: (teamId: number, playerId: number) => api<PlayerCard>(`/teams/${teamId}/players/${playerId}:unremove`, { method: 'POST' }),
  /** 매니저가 회원의 포지션을 고친다 — 이 팀에만 적용. 순서가 곧 선호 순서 */
  setMemberPositions: (teamId: number, playerId: number, positions: Position[]) =>
    api<PlayerCard>(`/teams/${teamId}/players/${playerId}/positions`, { method: 'PUT', body: { positions: positions.map((position) => ({ position })) } }),
  /** 팀장 넘기기 (팀장만) */
  transferOwner: (teamId: number, playerId: number) => api<TeamDetail>(`/teams/${teamId}:transfer-owner`, { method: 'POST', body: { player_id: playerId } }),

  leaderboard: (teamId: number, metric: LeaderboardMetric, period?: string) =>
    api<{ items: LeaderboardEntry[] }>(`/teams/${teamId}/stats/leaderboard?metric=${metric}${period ? `&period=${period}` : ''}`),
  /** 리더보드에서 고를 수 있는 달 (기록이 있는 달만, 최신순). 예: ["2026-09", "2026-08"] */
  leaderboardPeriods: (teamId: number) => api<{ items: string[] }>(`/teams/${teamId}/stats/periods`),
  /** 월간 코트 마진 랭킹 (기록 탭). period = "2026-09" */
  monthlyMargin: (teamId: number, period: string) => api<MonthlyMarginView>(`/teams/${teamId}/stats/monthly-margin?period=${period}`),

  // 게스트 레코드 (회차와 무관)
  guests: (teamId: number, q?: string) =>
    api<{ items: PlayerCard[] }>(`/teams/${teamId}/guests${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  mergeCandidates: (teamId: number) => api<{ items: MergeCandidate[] }>(`/teams/${teamId}/guests/merge-candidates`),
  mergeGuest: (guestPlayerId: number, intoPlayerId: number) =>
    api<PlayerCard>(`/players/${guestPlayerId}:merge`, { method: 'POST', body: { into_player_id: intoPlayerId } }),
  /** "다른 사람이에요" — 이름만 같은 짝을 후보에서 숨긴다(그 회원의 본인 확인 카드도) */
  dismissMergeCandidate: (teamId: number, guestPlayerId: number, memberPlayerId: number) =>
    api<void>(`/teams/${teamId}/guests/merge-candidates:dismiss`, { method: 'POST', body: { guest_player_id: guestPlayerId, member_player_id: memberPlayerId } }),
  /** 기록을 이어 준 게스트–회원 쌍 (되돌리기용) */
  mergedGuests: (teamId: number) => api<{ items: MergeCandidate[] }>(`/teams/${teamId}/guests/merged`),
  unmergeGuest: (guestPlayerId: number) => api<PlayerCard>(`/players/${guestPlayerId}:unmerge`, { method: 'POST' }),
  // 본인 확인 병합: 같은 이름의 게스트 기록을 회원이 직접 가져간다
  myGuestClaims: () => api<{ items: GuestClaimView[] }>('/me/guest-claims'),
  claimGuest: (guestPlayerId: number, accept: boolean) => api<{ items: GuestClaimView[] }>(`/players/${guestPlayerId}:claim`, { method: 'POST', body: { accept } }),
}
