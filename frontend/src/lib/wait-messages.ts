/**
 * 서버가 잠에서 깨는 동안(무료 등급 Render 는 한동안 요청이 없으면 멈췄다가 첫 요청에 30~60초 걸려 깬다)
 * 빙글빙글만 돌면 고장 난 줄 안다. 5초가 넘으면 농구 이야기로 기다림을 달랜다.
 */

export const WAIT_MESSAGES = [
  '코트 바닥 닦는 중…',
  '골망 새로 거는 중…',
  '공에 바람 넣는 중…',
  '농구화 끈 묶는 중…',
  '몸 풀고 레이업 몇 개 넣는 중…',
] as const

export const WAIT_SUBLINE = '처음 접속하면 최대 1분쯤 걸려요'

/** 이만큼 넘게 기다리면 문구를 띄운다 */
export const SLOW_AFTER_MS = 5_000
/** 문구를 바꾸는 간격 */
export const ROTATE_MS = 6_000

/** 무작위로 하나 고른다. 바로 앞 문구와는 겹치지 않게 (같은 문구가 연달아 나오면 멈춘 것처럼 보인다) */
export function pickWaitMessage(prev: string | null = null, rand: () => number = Math.random): string {
  const pool = prev === null ? [...WAIT_MESSAGES] : WAIT_MESSAGES.filter((m) => m !== prev)
  const i = Math.min(pool.length - 1, Math.floor(rand() * pool.length))
  return pool[i]
}
