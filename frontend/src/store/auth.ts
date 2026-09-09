/**
 * 로그인 상태 (zustand). 토큰은 localStorage 에 유지해 새로고침해도 로그인이 풀리지 않게 한다.
 * 사용자 정보(UserDetail)는 서버 상태이므로 여기 두지 않고 TanStack Query 로 조회한다.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { TokenPair } from '../api/types'
import { queryClient } from '../queryClient'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  setTokens: (pair: TokenPair) => void
  /** 로그인 — 캐시를 비우고 토큰을 넣는다 (다른 계정의 데이터가 남지 않게) */
  login: (pair: TokenPair) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      setTokens: (pair) => set({ accessToken: pair.access_token, refreshToken: pair.refresh_token }),
      login: (pair) => { queryClient.clear(); set({ accessToken: pair.access_token, refreshToken: pair.refresh_token }) },
      logout: () => { queryClient.clear(); set({ accessToken: null, refreshToken: null }) },
    }),
    { name: 'hooply-auth' },
  ),
)

export const useIsLoggedIn = () => useAuthStore((s) => s.accessToken !== null)
