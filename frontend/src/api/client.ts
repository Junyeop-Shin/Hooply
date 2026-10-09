/**
 * fetch 래퍼. Bearer 토큰 자동 첨부, 7.4절 오류 본문을 ApiError 로 변환, 401 시 refresh 1회 시도.
 */
import { useAuthStore } from '../store/auth'
import type { ErrorResponse, TokenPair } from './types'

import { API_ORIGIN } from '../lib/env'

export { API_ORIGIN }
const BASE = `${API_ORIGIN}/api/v1`

export class ApiError extends Error {
  status: number
  code: string
  details: ErrorResponse['details']
  constructor(status: number, body: ErrorResponse) {
    super(body.message)
    this.status = status
    this.code = body.code
    this.details = body.details ?? []
  }
}

/** 화면에 보여 줄 오류 문구 — 서버 문구(ApiError.message), 아니면 fallback */
export function errorMessage(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback
}

/** 배정 제약처럼 어떤 사람·그룹이 문제인지(details[].reason)까지 이어 붙여 보여 줄 때 */
export function errorMessageWithDetails(e: unknown, fallback: string): string {
  return e instanceof ApiError ? `${e.message}${e.details.length ? ' ' + e.details.map((d) => d.reason).join(' ') : ''}` : fallback
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ErrorResponse = { code: 'UNKNOWN', message: res.status >= 500 ? '문제가 생겼어요. 잠시 뒤 다시 해 주세요.' : '처리하지 못했어요. 화면을 새로고침한 뒤 다시 해 주세요.', details: [] }
  try {
    body = (await res.json()) as ErrorResponse
  } catch {
    /* 본문이 JSON 이 아니면 기본 메시지 유지 */
  }
  return new ApiError(res.status, body)
}

/** 응답을 이만큼 넘게 기다리면 끊는다. 무료 서버가 잠에서 깨는 데 30~60초 걸리므로 그보다 넉넉히 */
export const REQUEST_TIMEOUT_MS = 70_000
export const TIMEOUT_MESSAGE = '응답이 늦어지고 있어요. 잠시 뒤 다시 눌러 주세요.'

/** fetch + 시간 초과. 끊기면 ApiError(code=TIMEOUT) — 화면이 영원히 돌기만 하지 않게 */
async function fetchWithTimeout(url: string, init: RequestInit, ms = REQUEST_TIMEOUT_MS): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ms)
  try {
    return await fetch(url, { ...init, signal: ctrl.signal })
  } catch (e) {
    if (ctrl.signal.aborted) throw new ApiError(0, { code: 'TIMEOUT', message: TIMEOUT_MESSAGE, details: [] })
    throw e
  } finally {
    clearTimeout(timer)
  }
}

let refreshing: Promise<boolean> | null = null  // 동시에 여러 요청이 401 을 받아도 refresh 는 한 번만

/** 저장소(localStorage)에 다른 탭이 남긴 토큰이 있으면 그것으로 바꾼다. 바뀌었으면 true */
async function adoptStoredTokens(current: string | null): Promise<boolean> {
  try { await useAuthStore.persist.rehydrate() } catch { return false }
  const next = useAuthStore.getState().refreshToken
  return next !== null && next !== current
}

/**
 * access 만료 시 refresh. refresh 토큰은 한 번 쓰면 버려지므로(회전), 탭이 여러 개면 다른 탭이 먼저 바꿔 둔
 * 토큰이 저장소에 있을 수 있다 — 그때는 그 토큰을 받아 다시 시도하고, 로그아웃하지 않는다.
 */
async function tryRefresh(): Promise<boolean> {
  if (refreshing) return refreshing
  refreshing = (async () => {
    const before = useAuthStore.getState().refreshToken
    if (await adoptStoredTokens(before)) return true  // 다른 탭이 이미 회전했다
    const { refreshToken, setTokens, logout } = useAuthStore.getState()
    if (!refreshToken) { if (before) logout(); return false }  // 다른 탭에서 로그아웃했다
    let res: Response
    try {
      res = await fetchWithTimeout(`${BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refreshToken }) })
    } catch {
      return false  // 네트워크 오류·시간 초과: 로그아웃하지 않고 이번 요청만 실패시킨다
    }
    if (res.status === 401 || res.status === 403) {
      // 이 요청이 오가는 사이 다른 탭이 회전했을 수 있다 — 그 토큰이 있으면 그것으로
      if (await adoptStoredTokens(refreshToken)) return true
      logout(); return false  // 토큰이 정말 만료·무효일 때만 로그아웃
    }
    if (!res.ok) return false  // 서버 일시 오류
    setTokens((await res.json()) as TokenPair)
    return true
  })().finally(() => { refreshing = null })
  return refreshing
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const { method = 'GET', body, auth = true } = init
  const doFetch = () => {
    const headers: Record<string, string> = {}
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    const token = useAuthStore.getState().accessToken
    if (auth && token) headers.Authorization = `Bearer ${token}`
    return fetchWithTimeout(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  }

  let res = await doFetch()
  // access 만료(401) 이면 refresh 후 한 번만 재시도
  if (res.status === 401 && auth && (await tryRefresh())) res = await doFetch()

  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  // 본문이 비어 있으면(204 를 200 으로 바꾸는 중인 API 등) undefined
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}
