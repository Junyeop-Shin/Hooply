/** api() — 탭 사이 토큰 회전 · 응답 시간 초과 · 빈 본문 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AUTH_STORAGE_KEY, useAuthStore } from '../store/auth'
import { ApiError, REQUEST_TIMEOUT_MS, TIMEOUT_MESSAGE, api } from './client'

type FakeRes = { ok: boolean; status: number; json: () => Promise<unknown>; text: () => Promise<string> }
const res = (status: number, body?: unknown): FakeRes => ({
  ok: status >= 200 && status < 300, status,
  json: async () => body,
  text: async () => (body === undefined ? '' : JSON.stringify(body)),
})
const authOf = (init?: RequestInit) => (init?.headers as Record<string, string> | undefined)?.Authorization

describe('api()', () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: 'a1', refreshToken: 'r1' })
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); localStorage.clear() })

  it('다른 탭이 이미 토큰을 바꿨으면 refresh 하지 않고 그 토큰으로 다시 시도한다 (로그아웃 안 함)', async () => {
    // 다른 탭이 회전해 둔 토큰
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ state: { accessToken: 'a2', refreshToken: 'r2' }, version: 0 }))
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/refresh')) return res(401)
      return authOf(init) === 'Bearer a2' ? res(200, { ok: true }) : res(401, { code: 'TOKEN_EXPIRED', message: '만료', details: [] })
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(api<{ ok: boolean }>('/me')).resolves.toEqual({ ok: true })
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/auth/refresh'))).toBe(false)
    expect(useAuthStore.getState().refreshToken).toBe('r2')
  })

  it('저장소에도 새 토큰이 없으면 refresh 해서 새 토큰을 쓴다', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/refresh')) return res(200, { access_token: 'a3', refresh_token: 'r3', token_type: 'bearer' })
      return authOf(init) === 'Bearer a3' ? res(200, { ok: 1 }) : res(401)
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(api('/me')).resolves.toEqual({ ok: 1 })
    expect(useAuthStore.getState().accessToken).toBe('a3')
  })

  it('응답이 너무 늦으면 끊고 한국어 오류를 낸다', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => new Promise((_, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })))
    const p = api('/teams/1')
    const caught = p.catch((e: unknown) => e)
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 10)
    const err = await caught
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).code).toBe('TIMEOUT')
    expect((err as ApiError).message).toBe(TIMEOUT_MESSAGE)
  })

  it('본문이 빈 성공 응답은 undefined 로 끝난다 (204 · 빈 200 모두)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => res(200)))
    await expect(api('/me/password', { method: 'POST' })).resolves.toBeUndefined()
  })
})
