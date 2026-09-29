/**
 * 타자 치듯 글자를 드러내는 훅 (AI 설명 카드).
 *
 * 진짜 토큰 스트리밍은 쓰지 않는다 — 서버가 가드레일(가명·숫자·누설 검사)을 **다 통과한 뒤에만** 결과를 내주기 때문에,
 * 검사 전 문장이 화면에 먼저 보이면 안 된다. 대신 받은 결과를 한 글자씩 보여 줘서 쓰는 중인 느낌을 낸다.
 * 움직임 줄이기 설정이면 바로 전부 보여 준다.
 *
 * 한 번 끝까지 보여 준 글은 다시 타자 치지 않는다 — 화면을 옮겼다 돌아오거나, 배정을 바꿨다가 원래대로 돌려
 * 같은 설명이 다시 뜨면 바로 전부 보여 준다. 본 글은 글 내용의 해시로 기억한다 (이 탭이 열려 있는 동안, sessionStorage).
 */
import { useEffect, useState } from 'react'

const CPS = 55 // 초당 글자 수
const SEEN_STORE = 'hooply-typed'
const SEEN_MAX = 300

/** 글 내용 → 짧은 해시 (djb2). 본 글을 기억하는 데만 쓴다 */
function hash(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return (h >>> 0).toString(36) + s.length.toString(36)
}

const seen: Set<string> = (() => {
  try { return new Set(JSON.parse(sessionStorage.getItem(SEEN_STORE) ?? '[]') as string[]) } catch { return new Set<string>() }
})()

function markSeen(h: string) {
  if (seen.has(h)) return
  seen.add(h)
  try { sessionStorage.setItem(SEEN_STORE, JSON.stringify([...seen].slice(-SEEN_MAX))) } catch { /* 저장소 없음 */ }
}

function reducedMotion() {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** parts 를 앞에서부터 차례로 드러낸다. 반환: [부분별로 드러난 글자, 다 끝났는지] */
export function useTypewriter(parts: string[], enabled = true): [string[], boolean] {
  const key = parts.join('\u0000')
  const total = parts.reduce((a, p) => a + p.length, 0)
  const h = hash(key)
  const [st, setSt] = useState({ key: '', n: 0 })
  const already = seen.has(h) // 이미 한 번 끝까지 본 글
  const n = !enabled || reducedMotion() || already ? total : st.key === key ? st.n : 0

  useEffect(() => {
    if (!enabled || reducedMotion() || total === 0 || seen.has(h)) return
    const started = performance.now()
    const id = window.setInterval(() => {
      const shown = Math.min(total, Math.ceil(((performance.now() - started) / 1000) * CPS))
      setSt({ key, n: shown })
      if (shown >= total) { window.clearInterval(id); markSeen(h) }
    }, 30)
    return () => window.clearInterval(id)
  }, [key, h, total, enabled])

  // 부분마다 시작 위치(앞 부분 길이의 합)를 구해 거기서부터 n 까지만 자른다
  const starts = parts.map((_, i) => parts.slice(0, i).reduce((a, p) => a + p.length, 0))
  const out = parts.map((p, i) => p.slice(0, Math.max(0, Math.min(p.length, n - starts[i]))))
  return [out, n >= total]
}

/** 값이 ms 동안 바뀌지 않았을 때만 따라가는 값 (선수를 여러 번 옮기는 동안 AI 를 매번 부르지 않게) */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return v
}
