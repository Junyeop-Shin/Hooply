import { MutationCache, QueryClient } from '@tanstack/react-query'
import { ApiError, errorMessage } from './api/client'
import { toast } from './store/feedback'

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: {
      /** 화면이 오류를 직접(Alert 등) 보여 주면 true — 전역 토스트를 띄우지 않는다 */
      inlineError?: boolean
    }
  }
}

/**
 * 서버 상태 캐시. 로그인/로그아웃 시 반드시 비운다 — 이전 사용자의 팀 목록이 다음 사용자 화면에 남지 않게 (store/auth.ts)
 *
 * 변경(mutation)이 실패했는데 그 화면이 오류를 따로 다루지 않으면(onError 도 meta.inlineError 도 없으면)
 * 아무 반응 없이 끝나지 않도록 서버 문구를 토스트로 띄운다.
 */
export const queryClient = new QueryClient({
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      if (mutation.options.onError || mutation.meta?.inlineError) return
      toast(errorMessage(error, '요청을 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.'), 'error')
    },
  }),
  defaultOptions: {
    queries: {
      // 한 번 더 시도한다. 단 응답 시간 초과(서버가 70초 넘게 답이 없음)는 다시 기다리게 하지 않는다
      retry: (count, e) => count < 1 && !(e instanceof ApiError && e.code === 'TIMEOUT'),
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
