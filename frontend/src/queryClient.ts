import { QueryClient } from '@tanstack/react-query'

/** 서버 상태 캐시. 로그인/로그아웃 시 반드시 비운다 — 이전 사용자의 팀 목록이 다음 사용자 화면에 남지 않게 (store/auth.ts) */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      // 화면을 오갈 때마다 다시 받지 않도록 1분은 캐시를 그대로 쓴다. 값이 바뀌는 시점은 각 mutation 이 invalidate 로 알린다
      staleTime: 60_000,
      // 탭을 오래 비웠다 돌아와도 화면이 비지 않게 30분은 캐시를 들고 있는다 (기본 5분)
      gcTime: 30 * 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

/** 거의 바뀌지 않는 참조 데이터(설문 문항 등)용 — 한 번 받으면 다시 받지 않는다 */
export const STATIC_QUERY = { staleTime: Infinity, gcTime: Infinity } as const
