/**
 * 로그인하면 원래 가려던 화면으로 — 단톡방 초대 링크(/teams/join?code=…) · 투표 링크 · 배정 결과 링크를 로그인 전에 열면
 * 로그인 화면으로 보내면서 원래 주소를 버렸다(docs/09 3-1). 카카오 로그인은 카카오 사이트를 다녀오므로 화면 상태(state)로는
 * 못 넘기고 localStorage 에 잠깐 둔다. 한 시간이 지나면 버린다 — 다른 사람이 같은 기기에서 나중에 로그인할 때 엉뚱한 화면으로 가지 않게.
 *
 * 새로 가입한 사람도 가입 직후 그 주소로 간다 — 설문보다 팀 가입 · 참석 응답이 먼저다 (docs/10 F-3).
 */
const KEY = 'hooply-return-to'
const TTL_MS = 60 * 60 * 1000
/** 스스로 로그아웃한 직후 이 시간 동안은 주소를 맡기지 않는다 (forgetReturnTo) */
const FORGET_MS = 2000
let ignoreUntil = 0

/** 앱 안의 화면 주소만 — 다른 사이트 · 로그인 관련 화면은 받지 않는다 */
export function isSafeReturnPath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) return false
  const p = path.split(/[?#]/)[0]
  return p !== '/' && !['/login', '/signup', '/auth/', '/password/'].some((x) => p === x || p.startsWith(x.endsWith('/') ? x : `${x}/`))
}

export function saveReturnTo(path: string, now = Date.now()) {
  if (now < ignoreUntil || !isSafeReturnPath(path)) return
  try { localStorage.setItem(KEY, JSON.stringify({ path, at: now })) } catch { /* 저장소 없음 */ }
}

/** 남아 있는지만 본다 (지우지 않는다) */
export function peekReturnTo(now = Date.now()): string | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const { path, at } = JSON.parse(raw) as { path?: string; at?: number }
    if (!path || !at || now - at > TTL_MS || !isSafeReturnPath(path)) { localStorage.removeItem(KEY); return null }
    return path
  } catch { return null }
}

/**
 * 스스로 로그아웃할 때 부른다. 로그아웃하면 보던 화면(예: /me)에서 로그인 화면으로 튕기면서 가드가 그 주소를 맡기는데,
 * 그대로 두면 다음 로그인이 홈이 아니라 그 화면에서 시작한다 (다른 사람이 같은 기기로 로그인하면 남의 화면 주소다).
 * 맡겨 둔 주소를 지우고, 직후 잠깐 들어오는 주소도 받지 않는다. 로그인이 만료돼 튕긴 경우에는 부르지 않는다 — 그때는 보던 화면으로 돌아가는 게 맞다
 */
export function forgetReturnTo(now = Date.now()) {
  ignoreUntil = now + FORGET_MS
  try { localStorage.removeItem(KEY) } catch { /* 저장소 없음 */ }
}

/** 꺼내고 지운다 */
export function takeReturnTo(now = Date.now()): string | null {
  const path = peekReturnTo(now)
  try { localStorage.removeItem(KEY) } catch { /* 저장소 없음 */ }
  return path
}
