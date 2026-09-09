import { api } from './client'
import type { TeamMembershipView, TokenPair, UserDetail } from './types'

export interface SignupInput {
  email: string
  password: string
  name: string
  nickname?: string
  height_cm?: number
}

export const authApi = {
  signup: (input: SignupInput) =>
    api<TokenPair>('/auth/signup', { method: 'POST', body: input, auth: false }),
  login: (email: string, password: string) =>
    api<TokenPair>('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  me: () => api<UserDetail>('/me'),
  updateMe: (patch: Partial<Pick<UserDetail, 'name' | 'nickname' | 'height_cm' | 'primary_team_id'>>) =>
    api<UserDetail>('/me', { method: 'PATCH', body: patch }),
  myTeams: () => api<{ items: TeamMembershipView[] }>('/me/teams'),
}
