import { describe, expect, it } from 'vitest'
import { inSameLock, mergeLock } from './locks'

/** 그룹 안 순서·그룹 순서와 무관하게 비교한다 */
const norm = (groups: number[][]) => groups.map((g) => [...g].sort((a, b) => a - b)).sort((a, b) => a[0] - b[0])

describe('mergeLock', () => {
  it('겹치는 묶음이 없으면 새 묶음을 더한다', () => {
    expect(norm(mergeLock([[1, 2]], [3, 4]))).toEqual([[1, 2], [3, 4]])
  })

  it('이미 묶인 사람과 묶으면 기존 묶음에 추가된다 (마지막 요청으로 바꿔치기하지 않는다)', () => {
    // 참가자 A(1) 가 게스트 G1(10) 과 묶인 뒤 게스트 G2(11) 요청을 승인
    expect(norm(mergeLock([[10, 1]], [11, 1]))).toEqual([[1, 10, 11]])
  })

  it('한 참가자가 부른 게스트 셋을 차례로 승인하면 모두 한 묶음이 된다', () => {
    const groups = [[10, 1], [11, 1], [12, 1]].reduce(mergeLock, [] as number[][])
    expect(norm(groups)).toEqual([[1, 10, 11, 12]])
  })

  it('두 묶음에 걸친 요청이면 두 묶음이 하나로 합쳐진다', () => {
    expect(norm(mergeLock([[1, 2], [3, 4], [5, 6]], [2, 3]))).toEqual([[1, 2, 3, 4], [5, 6]])
  })

  it('합친 결과가 다른 묶음과 또 겹쳐도 끝까지 합친다', () => {
    expect(norm(mergeLock([[1, 2], [2, 3], [3, 4]], [1, 9]))).toEqual([[1, 2, 3, 4, 9]])
  })

  it('한 사람만 넘기면 묶음이 생기지 않는다', () => {
    expect(mergeLock([], [1])).toEqual([])
  })
})

describe('inSameLock', () => {
  it('같은 묶음에 있을 때만 true', () => {
    expect(inSameLock([[1, 2, 3]], 1, 3)).toBe(true)
    expect(inSameLock([[1, 2], [3, 4]], 1, 3)).toBe(false)
  })
})
