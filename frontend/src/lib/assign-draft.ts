/**
 * 배정 실행 화면(S-12)의 조건(묶기 · 갈라놓기 · 미리 배치)을 화면 밖에 보관하고 되살린다.
 * 결과 화면에 갔다가 돌아오거나 새로고침해도 걸어 둔 조건이 사라지지 않게 —
 *   1) 이 탭에서 고치던 조건(sessionStorage `assign-draft-{eventId}`)
 *   2) 없으면 이 일정의 마지막 배정 실행에 걸린 조건(GET /events/{id}/assignments)
 * 지금 참석자가 아닌 사람은 빼고, 2명이 안 남는 묶음 · 갈라놓기는 버린다.
 */
import type { ConstraintSet } from '../api/types'

export interface AssignDraft {
  locks: number[][]
  seps: number[][]
  /** player_id → 팀 번호 */
  pins: Record<number, number>
  three: boolean
}

export const assignDraftKey = (eventId: number) => `assign-draft-${eventId}`

export const isEmptyDraft = (d: Pick<AssignDraft, 'locks' | 'seps' | 'pins'>) =>
  d.locks.length === 0 && d.seps.length === 0 && Object.keys(d.pins).length === 0

/** 지금 참석자만 남긴다 */
export function keepAttendees(d: AssignDraft, attendees: Set<number>): AssignDraft {
  const groups = (gs: number[][]) => gs.map((g) => g.filter((p) => attendees.has(p))).filter((g) => g.length >= 2)
  return {
    locks: groups(d.locks),
    seps: groups(d.seps),
    pins: Object.fromEntries(Object.entries(d.pins).filter(([pid]) => attendees.has(Number(pid)))) as Record<number, number>,
    three: d.three,
  }
}

export function fromConstraintSet(c: ConstraintSet, teamCount = 2): AssignDraft {
  return {
    locks: c.lock_groups, seps: c.separate_groups,
    pins: Object.fromEntries(c.pins.map((p) => [p.player_id, p.squad_no])),
    three: teamCount === 3,
  }
}

export function readAssignDraft(eventId: number): AssignDraft | null {
  try {
    const raw = sessionStorage.getItem(assignDraftKey(eventId))
    if (!raw) return null
    const d = JSON.parse(raw) as Partial<AssignDraft>
    if (!Array.isArray(d.locks) || !Array.isArray(d.seps) || typeof d.pins !== 'object' || d.pins === null) return null
    return { locks: d.locks, seps: d.seps, pins: d.pins, three: !!d.three }
  } catch {
    return null  // 저장소를 못 쓰는 브라우저(사생활 보호 모드 등)
  }
}

export function writeAssignDraft(eventId: number, d: AssignDraft) {
  try { sessionStorage.setItem(assignDraftKey(eventId), JSON.stringify(d)) } catch { /* 저장소 없음 */ }
}
