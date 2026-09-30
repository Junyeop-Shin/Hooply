import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isChunkLoadError, reloadForNewVersion } from './stale-chunk'

describe('배포 뒤 예전 조각 파일', () => {
  const reload = vi.fn()
  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal('location', { ...window.location, reload })
    reload.mockClear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('브라우저마다 다른 문구를 알아본다', () => {
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/team-BRTh34Nh.js'))).toBe(true)
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true)
    expect(isChunkLoadError(new TypeError('error loading dynamically imported module'))).toBe(true)
    expect(isChunkLoadError(new Error('테스트용 오류'))).toBe(false)
  })

  it('한 번은 새로고침하고, 30초 안에 또 실패하면 반복하지 않는다', () => {
    expect(reloadForNewVersion()).toBe(true)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(reloadForNewVersion()).toBe(false)
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
