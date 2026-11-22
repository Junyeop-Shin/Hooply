/** 로그인 뒤 원래 화면으로 (docs/09 3-1) — 앱 안 주소만 받고, 한 시간이 지나면 버린다 */
import { beforeEach, describe, expect, it } from 'vitest'
import { forgetReturnTo, isSafeReturnPath, peekReturnTo, saveReturnTo, takeReturnTo } from './return-to'

describe('return-to', () => {
  beforeEach(() => { localStorage.clear(); forgetReturnTo(-10_000) })  // "맡기지 않는 시간"이 다음 테스트로 넘어가지 않게

  it('초대 링크 주소를 맡겼다가 한 번만 꺼낸다', () => {
    saveReturnTo('/teams/join?code=CTMATE26', 1000)
    expect(peekReturnTo(2000)).toBe('/teams/join?code=CTMATE26')
    expect(takeReturnTo(2000)).toBe('/teams/join?code=CTMATE26')
    expect(takeReturnTo(2000)).toBeNull()
  })

  // 로그아웃하면 보던 화면(/me)에서 로그인 화면으로 튕기면서 그 주소가 맡겨진다 — 다음 로그인이 프로필에서 시작하지 않게 버린다
  it('스스로 로그아웃한 직후에는 보던 화면을 맡기지 않고, 그 뒤의 초대 링크는 다시 맡긴다', () => {
    saveReturnTo('/events/12', 0)
    forgetReturnTo(1000)
    expect(peekReturnTo(1000)).toBeNull()  // 맡겨 둔 것도 지운다
    saveReturnTo('/me', 1500)              // 로그아웃 직후 가드가 맡기려는 주소
    expect(peekReturnTo(1600)).toBeNull()
    saveReturnTo('/teams/join?code=CTMATE26', 5000)
    expect(peekReturnTo(5100)).toBe('/teams/join?code=CTMATE26')
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
