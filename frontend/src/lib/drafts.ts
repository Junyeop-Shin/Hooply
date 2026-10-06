/**
 * 화면 입력의 임시 저장(초안) 키 접두어. 초안은 계정이 아니라 일정 · 설문 단위로 저장되므로,
 * 로그인 · 로그아웃 때 모두 지워 다른 계정의 초안이 다음 사람에게 이어지지 않게 한다 (store/auth).
 * 토큰 갱신(setTokens)에는 지우지 않는다 — 경기 기록 입력 중에 토큰이 바뀌어도 초안은 남아야 한다.
 *   survey-draft-<templateId>            온보딩 설문 답(sessionStorage)
 *   quarters-draft-<eventId>             쿼터 기록 입력(localStorage)
 *   assign-draft-<eventId>               배정 조건(sessionStorage)
 *   play-draft-<userId>-<teamId>-<playId|new>  전술 편집기(sessionStorage)
 */
export const DRAFT_PREFIXES = ['survey-draft-', 'quarters-draft-', 'assign-draft-', 'play-draft-'] as const

const isDraftKey = (key: string) => DRAFT_PREFIXES.some((p) => key.startsWith(p))

/** 두 저장소에서 초안 키를 모두 지운다. 저장소를 못 쓰는 브라우저에서는 조용히 넘어간다 */
export function clearDrafts(storages: Storage[] = [localStorage, sessionStorage]) {
  for (const st of storages) {
    try {
      const keys: string[] = []
      for (let i = 0; i < st.length; i++) { const k = st.key(i); if (k && isDraftKey(k)) keys.push(k) }
      keys.forEach((k) => st.removeItem(k))
    } catch { /* 저장소 없음 */ }
  }
}
