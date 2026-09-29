import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useTypewriter } from './typewriter'

describe('useTypewriter', () => {
  afterEach(() => vi.useRealTimers())

  it('앞 부분부터 차례로 드러나고 끝나면 done', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useTypewriter(['가나다', '라마']))
    expect(result.current[0]).toEqual(['', ''])
    act(() => { vi.advanceTimersByTime(60) })
    const [mid] = result.current
    expect(mid[0].length).toBeGreaterThan(0)
    expect(mid[1]).toBe(mid[0].length < 3 ? '' : mid[1])  // 앞 부분이 다 나오기 전엔 뒷부분이 비어 있다
    act(() => { vi.advanceTimersByTime(1000) })
    expect(result.current).toEqual([['가나다', '라마'], true])
  })

  it('끄면 바로 전부 보여 준다', () => {
    const { result } = renderHook(() => useTypewriter(['가나다'], false))
    expect(result.current).toEqual([['가나다'], true])
  })

  it('처음에는 한 글자씩, 한 번 끝까지 본 글은 다시 열어도 바로 전부 보여 준다', () => {
    vi.useFakeTimers()
    const parts = ['블랙은 골밑이 강해요', '화이트는 외곽이 강해요']
    const first = renderHook(() => useTypewriter(parts))
    expect(first.result.current[1]).toBe(false)
    expect(first.result.current[0][0].length).toBeLessThan(parts[0].length)
    act(() => { vi.advanceTimersByTime(3000) })
    expect(first.result.current).toEqual([parts, true])
    first.unmount()

    // 화면을 옮겼다 돌아온 것처럼 새로 마운트 — 타자 효과 없이 바로 끝
    const again = renderHook(() => useTypewriter(parts))
    expect(again.result.current).toEqual([parts, true])

    // 다른 글은 다시 타자 친다
    const other = renderHook(() => useTypewriter(['레드는 속공이 강해요']))
    expect(other.result.current[1]).toBe(false)
  })
})
