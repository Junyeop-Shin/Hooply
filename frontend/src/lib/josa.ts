/**
 * 한국어 조사를 앞말 받침에 맞춘다 — 백엔드 `app/core/josa.py` 와 같은 규칙.
 * 자리 번호({5})를 이름으로 바꿔 넣는 전술 대안 문장에 쓴다.
 */
const PAIRS: Record<string, [string, string]> = {}
for (const pair of [['이', '가'], ['은', '는'], ['을', '를'], ['과', '와'], ['으로', '로']] as [string, string][]) {
  PAIRS[pair[0]] = pair
  PAIRS[pair[1]] = pair
}
// 바로 뒤 조사. 보조사가 한 글자 더 붙은 겹조사("와는")까지. 다음 글자가 한글이면 낱말이라 건드리지 않는다
const PARTICLE = '(?:(으로|로|이|가|은|는|을|를|과|와)(?=(?:는|도|만|의|요)?(?![가-힣])))'

export function josa(word: string, particle: string): string {
  const pair = PAIRS[particle]
  const last = word.slice(-1)
  if (!pair || !(last >= '가' && last <= '힣')) return particle
  const final = (last.charCodeAt(0) - 0xac00) % 28 // 0 = 받침 없음, 8 = ㄹ
  if (pair[0] === '으로') return final === 0 || final === 8 ? '로' : '으로'
  return final ? pair[0] : pair[1]
}

/** token(첫 그룹 = 키)을 lookup 결과로 바꾸고 바로 뒤 조사를 맞춘다. lookup 이 null 이면 그대로 */
export function substitute(text: string, token: string, lookup: (key: string) => string | null): string {
  return text.replace(new RegExp(token + PARTICLE + '?', 'g'), (whole, key: string, particle?: string) => {
    const word = lookup(key)
    if (word === null) return whole
    return word + (particle ? josa(word, particle) : '')
  })
}
