import { afterEach, describe, expect, it } from 'vitest'
import { clearDrafts } from './drafts'

describe('clearDrafts', () => {
  afterEach(() => { localStorage.clear(); sessionStorage.clear() })

  it('두 저장소의 초안 키만 지우고 나머지는 남긴다', () => {
    localStorage.setItem('quarters-draft-3', '{}')
    localStorage.setItem('hooply-auth', 'keep')
    localStorage.setItem('hooply:records-seen-month:1', '2026-10')
    sessionStorage.setItem('survey-draft-2', '{}')
    sessionStorage.setItem('assign-draft-7', '{}')
    sessionStorage.setItem('play-draft-5-1-new', '{}')
    sessionStorage.setItem('other', 'keep')
    clearDrafts()
    expect(localStorage.getItem('quarters-draft-3')).toBeNull()
    expect(localStorage.getItem('hooply-auth')).toBe('keep')
    expect(localStorage.getItem('hooply:records-seen-month:1')).toBe('2026-10')
    expect(sessionStorage.getItem('survey-draft-2')).toBeNull()
    expect(sessionStorage.getItem('assign-draft-7')).toBeNull()
    expect(sessionStorage.getItem('play-draft-5-1-new')).toBeNull()
    expect(sessionStorage.getItem('other')).toBe('keep')
  })

  it('저장소를 못 써도 던지지 않는다', () => {
    const broken = { get length() { throw new Error('no storage') } } as unknown as Storage
    expect(() => clearDrafts([broken])).not.toThrow()
  })
})
