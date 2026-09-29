import { api } from './client'
import type { TeamMembershipView, TokenPair, UserDetail } from './types'

export const KAKAO_CALLBACK = () => `${window.location.origin}/auth/kakao/callback`

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
  forgotPassword: (email: string) => api<{ accepted: boolean }>('/auth/password/forgot', { method: 'POST', body: { email }, auth: false }),
  resetPassword: (token: string, new_password: string) => api<{ ok: boolean }>('/auth/password/reset', { method: 'POST', body: { token, new_password }, auth: false }),
  changePassword: (current_password: string, new_password: string) => api<void>('/me/password', { method: 'POST', body: { current_password, new_password } }),
  deleteMe: () => api<void>('/me', { method: 'DELETE' }),
  me: () => api<UserDetail>('/me'),
  setAvatar: (data_url: string) => api<UserDetail>('/me/avatar', { method: 'POST', body: { data_url } }),
  deleteAvatar: () => api<UserDetail>('/me/avatar', { method: 'DELETE' }),
  updateMe: (patch: Partial<Pick<UserDetail, 'name' | 'nickname' | 'height_cm' | 'primary_team_id'>>) =>
    api<UserDetail>('/me', { method: 'PATCH', body: patch }),
  myTeams: () => api<{ items: TeamMembershipView[] }>('/me/teams'),
  // 카카오 로그인 (11.5절): 인가 URL → 카카오 → /auth/kakao/callback?code&state → 백엔드 교환
  kakaoLoginUrl: () => api<{ url: string; state: string }>(`/auth/kakao/login-url?redirect_uri=${encodeURIComponent(KAKAO_CALLBACK())}`, { auth: false }),
  kakaoCallback: (code: string, state: string) =>
    api<TokenPair & { is_new: boolean }>(`/auth/kakao/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}&redirect_uri=${encodeURIComponent(KAKAO_CALLBACK())}`, { auth: false }),
  kakaoLink: (code: string, state: string) =>
    api<UserDetail>('/auth/kakao/link', { method: 'POST', body: { code, state, redirect_uri: KAKAO_CALLBACK() } }),
}
