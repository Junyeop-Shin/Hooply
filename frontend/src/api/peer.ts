import { api } from './client'
import type { CompatiblePlayer, PlayerStats, ShareMessage, VoteIn, VoteTargets } from './types'

/** 경기 후 피어 투표 (S-16) · 잘 맞는 참여자 (S-17). 종료 전에는 403 SURVEY_NOT_OPEN 이 온다 */
export const peerApi = {
  targets: (eventId: number) => api<VoteTargets>(`/events/${eventId}/post-game-survey`),
  submit: (eventId: number, votes: VoteIn[]) =>
    api<VoteTargets>(`/events/${eventId}/post-game-survey`, { method: 'POST', body: { votes } }),
  shareMessage: (eventId: number) => api<ShareMessage>(`/events/${eventId}/post-game-survey/share-message`),
  stats: (playerId: number) => api<PlayerStats>(`/players/${playerId}/stats`),
  compatible: (playerId: number) => api<{ items: CompatiblePlayer[] }>(`/players/${playerId}/compatible`),
}
