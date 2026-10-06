/**
 * 전술 편집기(S-30)의 편집 중 내용을 이 탭에 보관하고 되살린다 — 브라우저 뒤로 가기 · 제스처 · 새로고침으로 나갔다가 돌아와도
 * 그리던 전술이 사라지지 않게. 키는 `play-draft-<userId>-<teamId>-<playId|new>` (sessionStorage). 저장 · 지우기 때 지운다.
 * 되살리는 조건: 초안이 있고, 서버 전술보다 뒤에 저장했고(updatedAt), 이 화면을 열었을 때의 내용과 다를 때. 되살릴지는 화면이 묻는다.
 */
import type { CourtPoint, OppDefense, PlayStep, RoleSource, ScreenCall, Situation, TacticRole } from '../api/types'

export interface PlayDraftBody {
  name: string
  summary: string
  oppDefense: OppDefense
  screenCall: ScreenCall
  situation: Situation
  counter: string
  start: CourtPoint[]
  ball: number
  steps: PlayStep[]
  /** 설명을 직접 고친 단계 번호 */
  edited: number[]
  roles: TacticRole[] | null
  roleSource: RoleSource
}
export interface PlayDraft extends PlayDraftBody { savedAt: string }

export const playDraftKey = (userId: number, teamId: number, playId: number | null) => `play-draft-${userId}-${teamId}-${playId ?? 'new'}`

/** 비교용 — 키 순서를 고정하고 edited 는 정렬한다 */
const normalize = (d: PlayDraftBody): PlayDraftBody => ({
  name: d.name, summary: d.summary, oppDefense: d.oppDefense, screenCall: d.screenCall, situation: d.situation, counter: d.counter,
  start: d.start, ball: d.ball, steps: d.steps, edited: [...d.edited].sort((a, b) => a - b), roles: d.roles, roleSource: d.roleSource,
})
export const samePlayDraft = (a: PlayDraftBody, b: PlayDraftBody) => JSON.stringify(normalize(a)) === JSON.stringify(normalize(b))

const KEYS: (keyof PlayDraftBody)[] = ['name', 'summary', 'oppDefense', 'screenCall', 'situation', 'counter', 'start', 'ball', 'steps', 'edited', 'roles', 'roleSource']

/**
 * 되살릴 초안. 없거나 깨졌거나, 서버 전술이 더 새것이거나(다른 곳에서 고쳐 저장함), 열었을 때의 내용과 같으면 null —
 * 같거나 낡은 초안은 지운다
 */
export function readPlayDraft(key: string, opts: { updatedAt: string | null; initial: PlayDraftBody }): PlayDraft | null {
  let d: PlayDraft
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    d = JSON.parse(raw) as PlayDraft
    if (!d || typeof d !== 'object' || typeof d.savedAt !== 'string' || KEYS.some((k) => !(k in d)) || !Array.isArray(d.steps) || !Array.isArray(d.start)) {
      clearPlayDraft(key); return null
    }
  } catch { return null }
  const stale = opts.updatedAt !== null && Date.parse(d.savedAt) <= Date.parse(opts.updatedAt)
  if (stale || samePlayDraft(d, opts.initial)) { clearPlayDraft(key); return null }
  return d
}

export function writePlayDraft(key: string, body: PlayDraftBody, now: Date = new Date()) {
  try { sessionStorage.setItem(key, JSON.stringify({ ...normalize(body), savedAt: now.toISOString() })) } catch { /* 저장소 없음 */ }
}

export function clearPlayDraft(key: string) {
  try { sessionStorage.removeItem(key) } catch { /* ignore */ }
}
