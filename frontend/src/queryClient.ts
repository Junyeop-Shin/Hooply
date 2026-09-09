import { QueryClient } from '@tanstack/react-query'

/** 서버 상태 캐시. 로그인/로그아웃 시 반드시 비운다 — 이전 사용자의 팀 목록이 다음 사용자 화면에 남지 않게 (store/auth.ts) */
export const queryClient = new QueryClient({
  // 화면 전환마다 재요청하지 않도록 30초 동안은 캐시를 신선한 것으로 본다. 변경은 각 mutation 이 invalidate 한다
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false } },
})
