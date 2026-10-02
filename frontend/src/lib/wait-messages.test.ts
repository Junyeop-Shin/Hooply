import { describe, expect, it } from 'vitest'
import { WAIT_MESSAGES, pickWaitMessage } from './wait-messages'

describe('pickWaitMessage', () => {
  it('다섯 문구 중 하나를 고른다', () => {
    expect(WAIT_MESSAGES).toHaveLength(5)
    for (let i = 0; i < 50; i++) expect(WAIT_MESSAGES).toContain(pickWaitMessage())
  })

  it('난수 값에 따라 처음부터 끝까지 고를 수 있다 (1에 가까운 값도 범위를 넘지 않는다)', () => {
    expect(pickWaitMessage(null, () => 0)).toBe(WAIT_MESSAGES[0])
    expect(pickWaitMessage(null, () => 0.9999)).toBe(WAIT_MESSAGES[4])
    expect(pickWaitMessage(null, () => 1)).toBe(WAIT_MESSAGES[4])
  })

  it('바로 앞 문구는 다시 고르지 않는다', () => {
    for (const prev of WAIT_MESSAGES) {
      for (const r of [0, 0.3, 0.6, 0.99]) expect(pickWaitMessage(prev, () => r)).not.toBe(prev)
    }
  })
})
