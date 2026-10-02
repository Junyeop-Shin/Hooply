import { afterEach, describe, expect, it } from 'vitest'
import { fromConstraintSet, isEmptyDraft, keepAttendees, readAssignDraft, writeAssignDraft } from './assign-draft'

describe('배정 조건 보관', () => {
  afterEach(() => sessionStorage.clear())

  it('저장한 조건을 그대로 되살린다', () => {
    writeAssignDraft(7, { locks: [[1, 2]], seps: [[3, 4]], pins: { 5: 2 }, three: true })
    expect(readAssignDraft(7)).toEqual({ locks: [[1, 2]], seps: [[3, 4]], pins: { 5: 2 }, three: true })
    expect(readAssignDraft(8)).toBeNull()
  })

  it('깨진 값은 무시한다', () => {
    sessionStorage.setItem('assign-draft-9', '{"locks": 1}')
    expect(readAssignDraft(9)).toBeNull()
    sessionStorage.setItem('assign-draft-9', 'not json')
    expect(readAssignDraft(9)).toBeNull()
  })

  it('마지막 실행의 제약을 화면 상태로 바꾼다', () => {
    const d = fromConstraintSet({ lock_groups: [[1, 2, 3]], separate_groups: [[4, 5]], pins: [{ player_id: 6, squad_no: 1 }] }, 3)
    expect(d).toEqual({ locks: [[1, 2, 3]], seps: [[4, 5]], pins: { 6: 1 }, three: true })
  })

  it('불참이 된 사람은 빼고, 2명이 안 남는 묶음은 버린다', () => {
    const d = keepAttendees({ locks: [[1, 2, 3], [4, 5]], seps: [[6, 7]], pins: { 8: 1, 9: 2 }, three: false }, new Set([1, 2, 4, 6, 7, 9]))
    expect(d).toEqual({ locks: [[1, 2]], seps: [[6, 7]], pins: { 9: 2 }, three: false })
    expect(isEmptyDraft(keepAttendees(d, new Set()))).toBe(true)
  })
})
