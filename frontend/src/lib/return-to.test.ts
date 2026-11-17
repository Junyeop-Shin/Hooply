/** 로그인 뒤 원래 화면으로 (docs/09 3-1) — 앱 안 주소만 받고, 한 시간이 지나면 버린다 */
import { beforeEach, describe, expect, it } from 'vitest'
import { isSafeReturnPath, peekReturnTo, saveReturnTo, takeReturnTo } from './return-to'

describe('return-to', () => {
  beforeEach(() => localStorage.clear())

  it('초대 링크 주소를 맡겼다가 한 번만 꺼낸다', () => {
    saveReturnTo('/teams/join?code=CTMATE26', 1000)
    expect(peekReturnTo(2000)).toBe('/teams/join?code=CTMATE26')
    expect(takeReturnTo(2000)).toBe('/teams/join?code=CTMATE26')
    expect(takeReturnTo(2000)).toBeNull()
  })

  it('한 시간이 지나면 버린다', () => {
    saveReturnTo('/events/12/vote', 0)
    expect(takeReturnTo(60 * 60 * 1000 + 1)).toBeNull()
  })

  it('다른 사이트 · 로그인 화면 · 홈은 받지 않는다', () => {
    for (const p of ['https://evil.example', '//evil.example', '/\\evil', '/login', '/signup?x=1', '/auth/kakao/callback', '/password/reset?token=a', '/']) {
      expect(isSafeReturnPath(p)).toBe(false)
    }
    expect(isSafeReturnPath('/teams/join?code=AB')).toBe(true)
    expect(isSafeReturnPath('/loginx')).toBe(true)
  })
})
