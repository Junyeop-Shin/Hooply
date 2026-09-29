/**
 * 전술판 재생 계산 (docs/07 FR-47). 화면과 무관한 순수 함수만 둔다.
 *
 * 재생 위치는 `cursor` 하나로 나타낸다. 0 = 시작 위치, k = k단계까지 끝난 상태, 그 사이 소수 = k+1단계를 재생 중.
 * 단계마다 끝난 뒤의 위치·공 가진 슬롯을 미리 계산해 두고(stepStates), 프레임은 그 사이를 보간한다(frameAt).
 */
import { RIM_X, RIM_Y, COURT_H, COURT_W } from './court'
import type { CourtPoint, Defense, Play, PlayAction, PlayActionType, TacticRole } from '../api/types'
import { substitute } from './josa'

/** 막혔을 때의 대안: "{5}의 롤이 막히면 {2}에게" → 이름(없으면 "5번")으로. 조사는 받침에 맞춘다 */
export function renderCounter(text: string, names?: (string | null)[]): string {
  return substitute(text, '\\{([1-5])\\}', (k) => names?.[Number(k) - 1] ?? `${k}번`)
}

/** 동작 이름 — 백엔드 app/tactics/play.ACTION_LABEL 과 같다 */
export const ACTION_LABEL: Record<PlayActionType, string> = {
  move: '이동', dribble: '드리블', pass: '패스', screen: '스크린', cut: '컷', handoff: '핸드오프', shot: '슛',
}

export const ROLE_LABEL: Record<TacticRole, string> = {
  ball_handler: '볼 핸들러',
  screener_roll: '스크리너(롤)',
  screener_pop: '스크리너(팝)',
  shooter: '슈터',
  cutter: '커터',
  post: '포스트',
  spacer: '스페이서',
}

export const DEFENSE_LABEL: Record<Defense, string> = {
  man: '맨투맨 수비 상대',
  zone: '지역 수비 상대',
  any: '어느 수비든',
}

/** 림 중심 (0~1 좌표) — 슛하면 공이 여기로 간다 */
export const RIM: CourtPoint = { x: RIM_X / COURT_W, y: RIM_Y / COURT_H }

export interface StepState {
  pos: CourtPoint[] // pos[i] = 슬롯 i+1 위치
  holder: number | null // 공을 가진 슬롯 (슛한 뒤엔 null)
}

const BALL_ACTIONS = new Set(['dribble', 'pass', 'handoff', 'shot'])

/** 단계별 끝난 뒤 상태. 길이 = 단계 수 + 1 (0번째는 시작 위치) */
export function stepStates(play: Play): StepState[] {
  const out: StepState[] = [{ pos: play.start.map((p) => ({ ...p })), holder: play.ball }]
  for (const step of play.steps) {
    const prev = out[out.length - 1]
    const pos = prev.pos.map((p) => ({ ...p }))
    let holder = prev.holder
    for (const a of step.actions) {
      if (a.to) pos[a.slot - 1] = { ...a.to }
      if (a.slot === prev.holder && (a.type === 'pass' || a.type === 'handoff')) holder = a.target
      if (a.slot === prev.holder && a.type === 'shot') holder = null
    }
    out.push({ pos, holder })
  }
  return out
}

/** 그 단계의 공 동작 (공을 가진 슬롯이 한 것 하나) */
export function ballAction(play: Play, stepIndex: number, holder: number | null): PlayAction | undefined {
  return play.steps[stepIndex]?.actions.find((a) => a.slot === holder && BALL_ACTIONS.has(a.type))
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const lerp = (a: CourtPoint, b: CourtPoint, t: number): CourtPoint => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })

export interface Frame {
  pos: CourtPoint[]
  ball: CourtPoint
  ballOffset: number // 1 = 선수 옆에 붙여 그린다(번호를 가리지 않게), 0 = 제자리(림). 슛은 날아가며 줄어든다
}

/** cursor 위치의 프레임. cursor 는 0 ~ 단계 수 */
export function frameAt(play: Play, states: StepState[], cursor: number): Frame {
  const n = play.steps.length
  const c = Math.min(Math.max(cursor, 0), n)
  if (c === 0 || n === 0) {
    const s = states[0]
    return { pos: s.pos, ball: s.holder ? s.pos[s.holder - 1] : RIM, ballOffset: s.holder ? 1 : 0 }
  }
  const k = Math.min(Math.floor(c), n - 1)
  const t = ease(c - k)
  const from = states[k], to = states[k + 1]
  const pos = from.pos.map((p, i) => lerp(p, to.pos[i], t))
  const a = ballAction(play, k, from.holder)
  if (from.holder === null) return { pos, ball: RIM, ballOffset: 0 }
  const holderPos = pos[from.holder - 1]
  if (a && (a.type === 'pass' || a.type === 'handoff') && a.target) {
    return { pos, ball: lerp(holderPos, pos[a.target - 1], t), ballOffset: 1 }
  }
  if (a && a.type === 'shot') return { pos, ball: lerp(holderPos, RIM, t), ballOffset: 1 - t }
  return { pos, ball: holderPos, ballOffset: 1 }
}

/** cursor 에서 화살표·설명으로 보여 줄 단계 번호 (0부터). 멈춰 있으면 다음에 할 단계, 재생 중이면 지금 단계. 끝이면 null */
export function shownStep(play: Play, cursor: number): number | null {
  const n = play.steps.length
  if (n === 0 || cursor >= n) return null
  return Math.min(Math.max(Math.floor(cursor), 0), n - 1)
}

/** 드리블 화살표용 지그재그 경로 (SVG 좌표). 끝 20% 는 곧게 두어 화살촉이 똑바로 선다 */
export function zigzag(x1: number, y1: number, x2: number, y2: number, amp = 1.6, wave = 5): string {
  const dx = x2 - x1, dy = y2 - y1
  const len = Math.hypot(dx, dy)
  if (len < 1) return `M${x1},${y1} L${x2},${y2}`
  const ux = dx / len, uy = dy / len
  const nx = -uy, ny = ux
  const straight = Math.min(len * 0.2, 6)
  const zlen = len - straight
  const count = Math.max(2, Math.round(zlen / wave))
  const pts: string[] = [`M${x1.toFixed(2)},${y1.toFixed(2)}`]
  for (let i = 1; i <= count; i++) {
    const d = (i / count) * zlen
    const s = i === count ? 0 : (i % 2 ? amp : -amp)
    pts.push(`L${(x1 + ux * d + nx * s).toFixed(2)},${(y1 + uy * d + ny * s).toFixed(2)}`)
  }
  pts.push(`L${x2.toFixed(2)},${y2.toFixed(2)}`)
  return pts.join(' ')
}
