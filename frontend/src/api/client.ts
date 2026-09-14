/**
 * fetch 래퍼. Bearer 토큰 자동 첨부, 7.4절 오류 본문을 ApiError 로 변환, 401 시 refresh 1회 시도.
 */
import { useAuthStore } from '../store/auth'
import type { ErrorResponse, TokenPair } from './types'

// 같은 도메인에 nginx 프록시가 있으면 비워 두고(기본), 프론트와 API 를 따로 배포하면 VITE_API_URL=https://api.example.com 으로 지정
export const API_ORIGIN = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''
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

async function parseError(res: Response): Promise<ApiError> {
  let body: ErrorResponse = { code: 'UNKNOWN', message: res.status >= 500 ? '문제가 생겼어요. 잠시 후 다시 시도해 주세요.' : '요청을 처리하지 못했어요.', details: [] }
  try {
    body = (await res.json()) as ErrorResponse
  } catch {
    /* 본문이 JSON 이 아니면 기본 메시지 유지 */
  }
  return new ApiError(res.status, body)
}

let refreshing: Promise<boolean> | null = null  // 동시에 여러 요청이 401 을 받아도 refresh 는 한 번만

async function tryRefresh(): Promise<boolean> {
  if (refreshing) return refreshing
  refreshing = (async () => {
    const { refreshToken, setTokens, logout } = useAuthStore.getState()
    if (!refreshToken) return false
    let res: Response
    try {
      res = await fetch(`${BASE}/auth/refresh`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: refreshToken }) })
    } catch {
      return false  // 네트워크 오류: 로그아웃하지 않고 이번 요청만 실패시킨다
    }
    if (res.status === 401 || res.status === 403) { logout(); return false }  // 토큰이 정말 만료·무효일 때만 로그아웃
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
    return fetch(`${BASE}${path}`, {
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
  return (await res.json()) as T
}
