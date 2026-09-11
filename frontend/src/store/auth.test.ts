import { beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../queryClient'
import { useAuthStore } from './auth'

describe('auth store', () => {
  beforeEach(() => { useAuthStore.getState().logout(); vi.restoreAllMocks() })

  it('로그인하면 이전 계정의 서버 캐시를 비운다 (다른 사람 팀 목록이 남지 않게)', () => {
    const clear = vi.spyOn(queryClient, 'clear')
    useAuthStore.getState().login({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' })
    expect(clear).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().accessToken).toBe('a')
  })

  it('로그아웃도 캐시를 비우고 토큰을 지운다', () => {
    useAuthStore.getState().setTokens({ access_token: 'a', refresh_token: 'r', token_type: 'bearer' })
    const clear = vi.spyOn(queryClient, 'clear')
    useAuthStore.getState().logout()
    expect(clear).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().accessToken).toBeNull()
  })

  it('토큰 갱신(setTokens)은 캐시를 유지한다', () => {
    const clear = vi.spyOn(queryClient, 'clear')
    useAuthStore.getState().setTokens({ access_token: 'b', refresh_token: 'r2', token_type: 'bearer' })
    expect(clear).not.toHaveBeenCalled()
  })
})
