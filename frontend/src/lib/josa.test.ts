import { describe, expect, it } from 'vitest'
import { josa, substitute } from './josa'
import { renderCounter } from './tactics'

describe('josa', () => {
  it('받침에 맞춘다', () => {
    expect(josa('허재', '이')).toBe('가')
    expect(josa('서장훈', '가')).toBe('이')
    expect(josa('서장훈', '로')).toBe('으로')
    expect(josa('5번', '가')).toBe('이')
    expect(josa('PG', '이')).toBe('이') // 한글로 안 끝나면 그대로
  })
  it('자리 번호를 이름으로 바꾸고 조사를 맞춘다 (백엔드 render_counter 와 같은 결과)', () => {
    const t = '{3}이 바로 골밑으로, {1}은 윙에서, {2}와는'
    expect(renderCounter(t, ['허재', '서장훈', '허재'])).toBe('허재가 바로 골밑으로, 허재는 윙에서, 서장훈과는')
    expect(renderCounter('{3}이 바로, {1}은')).toBe('3번이 바로, 1번은')
    expect(substitute('{9}는', '\\{([1-5])\\}', () => 'x')).toBe('{9}는')
  })
})
