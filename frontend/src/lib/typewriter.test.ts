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
})
