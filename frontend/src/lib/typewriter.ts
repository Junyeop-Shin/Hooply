/**
 * 타자 치듯 글자를 드러내는 훅 (AI 설명 카드).
 *
 * 진짜 토큰 스트리밍은 쓰지 않는다 — 서버가 가드레일(가명·숫자·누설 검사)을 **다 통과한 뒤에만** 결과를 내주기 때문에,
 * 검사 전 문장이 화면에 먼저 보이면 안 된다. 대신 받은 결과를 한 글자씩 보여 줘서 쓰는 중인 느낌을 낸다.
 * 움직임 줄이기 설정이면 바로 전부 보여 준다.
 */
import { useEffect, useState } from 'react'

const CPS = 55 // 초당 글자 수

function reducedMotion() {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** parts 를 앞에서부터 차례로 드러낸다. 반환: [부분별로 드러난 글자, 다 끝났는지] */
export function useTypewriter(parts: string[], enabled = true): [string[], boolean] {
  const key = parts.join('\u0000')
  const total = parts.reduce((a, p) => a + p.length, 0)
  const [st, setSt] = useState({ key: '', n: 0 })
  const n = !enabled || reducedMotion() ? total : st.key === key ? st.n : 0

  useEffect(() => {
    if (!enabled || reducedMotion() || total === 0) return
    const started = performance.now()
    const id = window.setInterval(() => {
      const shown = Math.min(total, Math.ceil(((performance.now() - started) / 1000) * CPS))
      setSt({ key, n: shown })
      if (shown >= total) window.clearInterval(id)
    }, 30)
    return () => window.clearInterval(id)
  }, [key, total, enabled])

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
