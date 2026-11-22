/**
 * 내 정보 · 내 팀. 홈 · 프로필 · 일정 · 하단 메뉴가 같은 캐시를 쓴다.
 * 바꾸는 쪽(가입 · 설문 · 기본 팀 변경)이 늘 invalidate 하므로 화면을 옮길 때마다 다시 받지 않는다 (ME_STALE).
 */
import { useQuery } from '@tanstack/react-query'
import { authApi, ME_STALE } from '../api/auth'

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: authApi.me, staleTime: ME_STALE })
}

export function useMyTeams() {
  return useQuery({ queryKey: ['me', 'teams'], queryFn: authApi.myTeams, staleTime: ME_STALE })
}
