/**
 * 로그인하면 원래 가려던 화면으로 — 단톡방 초대 링크(/teams/join?code=…) · 투표 링크 · 배정 결과 링크를 로그인 전에 열면
 * 로그인 화면으로 보내면서 원래 주소를 버렸다(docs/09 3-1). 카카오 로그인은 카카오 사이트를 다녀오므로 화면 상태(state)로는
 * 못 넘기고 localStorage 에 잠깐 둔다. 한 시간이 지나면 버린다 — 다른 사람이 같은 기기에서 나중에 로그인할 때 엉뚱한 화면으로 가지 않게.
 *
 * 새로 가입한 사람은 설문을 먼저 하고(설계 흐름 A) 설문을 마칠 때 꺼내 쓴다.
 */
const KEY = 'hooply-return-to'
const TTL_MS = 60 * 60 * 1000

/** 앱 안의 화면 주소만 — 다른 사이트 · 로그인 관련 화면은 받지 않는다 */
export function isSafeReturnPath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return false
  const p = path.split(/[?#]/)[0]
  return p !== '/' && !['/login', '/signup', '/auth/', '/password/'].some((x) => p === x || p.startsWith(x.endsWith('/') ? x : `${x}/`))
}

export function saveReturnTo(path: string, now = Date.now()) {
  if (!isSafeReturnPath(path)) return
  try { localStorage.setItem(KEY, JSON.stringify({ path, at: now })) } catch { /* 저장소 없음 */ }
}

/** 남아 있는지만 본다 (지우지 않는다) — 새 가입자를 설문으로 먼저 보낼지 정할 때 */
export function peekReturnTo(now = Date.now()): string | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const { path, at } = JSON.parse(raw) as { path?: string; at?: number }
    if (!path || !at || now - at > TTL_MS || !isSafeReturnPath(path)) { localStorage.removeItem(KEY); return null }
    return path
  } catch { return null }
}

/** 꺼내고 지운다 */
export function takeReturnTo(now = Date.now()): string | null {
  const path = peekReturnTo(now)
  try { localStorage.removeItem(KEY) } catch { /* 저장소 없음 */ }
  return path
}
