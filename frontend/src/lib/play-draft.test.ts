import { afterEach, describe, expect, it } from 'vitest'
import { clearPlayDraft, playDraftKey, readPlayDraft, samePlayDraft, writePlayDraft, type PlayDraftBody } from './play-draft'

const initial: PlayDraftBody = {
  name: '', summary: '', oppDefense: 'man', screenCall: 'stay', situation: 'half_court', counter: '',
  start: [{ x: 0.5, y: 0.6 }], ball: 1, steps: [], edited: [], roles: null, roleSource: 'RULE',
}
const key = playDraftKey(5, 2, null)

describe('전술 편집 초안', () => {
  afterEach(() => sessionStorage.clear())

  it('키는 사용자 · 팀 · 전술(새 전술이면 new)로 나뉜다', () => {
    expect(key).toBe('play-draft-5-2-new')
    expect(playDraftKey(5, 2, 12)).toBe('play-draft-5-2-12')
  })

  it('고친 내용이 있으면 되살리고, 열었을 때와 같으면 지우고 null', () => {
    writePlayDraft(key, { ...initial, name: '우리 픽앤롤', steps: [{ caption: '', actions: [] }] })
    const d = readPlayDraft(key, { updatedAt: null, initial })
    expect(d?.name).toBe('우리 픽앤롤')
    expect(d?.steps).toHaveLength(1)

    writePlayDraft(key, { ...initial, edited: [] })
    expect(readPlayDraft(key, { updatedAt: null, initial })).toBeNull()
    expect(sessionStorage.getItem(key)).toBeNull()
  })

  it('서버 전술이 초안보다 새것이면(다른 곳에서 고쳐 저장) 초안을 버린다', () => {
    writePlayDraft(key, { ...initial, name: '옛 초안' }, new Date('2026-10-01T10:00:00Z'))
    expect(readPlayDraft(key, { updatedAt: '2026-10-02T10:00:00Z', initial })).toBeNull()
    writePlayDraft(key, { ...initial, name: '새 초안' }, new Date('2026-10-03T10:00:00Z'))
    expect(readPlayDraft(key, { updatedAt: '2026-10-02T10:00:00Z', initial })?.name).toBe('새 초안')
  })

  it('깨진 값은 무시하고, 지우면 없다', () => {
    sessionStorage.setItem(key, '{"name": 1}')
    expect(readPlayDraft(key, { updatedAt: null, initial })).toBeNull()
    sessionStorage.setItem(key, 'not json')
    expect(readPlayDraft(key, { updatedAt: null, initial })).toBeNull()
    writePlayDraft(key, { ...initial, name: 'x' })
    clearPlayDraft(key)
    expect(readPlayDraft(key, { updatedAt: null, initial })).toBeNull()
  })

  it('edited 순서가 달라도 같은 초안이다', () => {
    expect(samePlayDraft({ ...initial, edited: [2, 0] }, { ...initial, edited: [0, 2] })).toBe(true)
    expect(samePlayDraft({ ...initial, ball: 2 }, initial)).toBe(false)
  })
})
