/**
 * 로그인 상태 (zustand). 토큰은 localStorage 에 유지해 새로고침해도 로그인이 풀리지 않게 한다.
 * 사용자 정보(UserDetail)는 서버 상태이므로 여기 두지 않고 TanStack Query 로 조회한다.
 */
import { create } from 'zustand'
import { API_ORIGIN } from '../lib/env'
import { clearDrafts } from '../lib/drafts'
import { persist } from 'zustand/middleware'
import type { TokenPair } from '../api/types'
import { queryClient } from '../queryClient'

/** localStorage 키 (zustand persist) */
export const AUTH_STORAGE_KEY = 'hooply-auth'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  setTokens: (pair: TokenPair) => void
  /** 로그인 — 캐시와 화면 초안(lib/drafts)을 비우고 토큰을 넣는다 (다른 계정의 데이터 · 입력이 남지 않게) */
  login: (pair: TokenPair) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      setTokens: (pair) => set({ accessToken: pair.access_token, refreshToken: pair.refresh_token }),
      login: (pair) => { queryClient.clear(); clearDrafts(); set({ accessToken: pair.access_token, refreshToken: pair.refresh_token }) },
      logout: () => {
        const refresh = useAuthStore.getState().refreshToken
        if (refresh) {
          // api() 를 쓰면 client ↔ store 순환 import 라 fetch 를 직접 쓴다. keepalive: 화면을 닫아도 요청은 끝까지 간다
          fetch(`${API_ORIGIN}/api/v1/auth/logout`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refresh }), keepalive: true }).catch(() => {})
        }
        queryClient.clear(); clearDrafts(); set({ accessToken: null, refreshToken: null })
      },
    }),
    { name: AUTH_STORAGE_KEY },
  ),
)

/**
 * 탭끼리 토큰 맞추기. 다른 탭이 refresh 로 토큰을 바꾸거나(회전) 로그아웃하면 localStorage 가 바뀌고
 * 이 탭에는 'storage' 이벤트가 온다 — 그 값을 읽어 와서, 이미 버려진 refresh 토큰으로 요청하다 로그아웃되지 않게 한다.
 */
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== null && e.key !== AUTH_STORAGE_KEY) return  // key=null 은 저장소 전체 비우기
    const wasLoggedIn = useAuthStore.getState().accessToken !== null
    Promise.resolve(useAuthStore.persist.rehydrate()).then(() => {
      if (e.newValue === null) useAuthStore.setState({ accessToken: null, refreshToken: null })  // 키가 지워졌다
      // 다른 탭에서 로그아웃했다 → 이 탭의 서버 캐시도 비운다 (화면은 RequireAuth 가 로그인으로 보낸다)
      if (wasLoggedIn && useAuthStore.getState().accessToken === null) queryClient.clear()
    }).catch(() => { /* 저장소를 못 읽으면 그대로 */ })
  })
}

export const useIsLoggedIn = () => useAuthStore((s) => s.accessToken !== null)
