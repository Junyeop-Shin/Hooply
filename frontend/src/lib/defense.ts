/**
 * 수비 움직임 시뮬레이션 (docs/07 FR-55 · FR-56). 화면과 무관한 순수 함수만 둔다.
 *
 * 공격 전술(lib/tactics 의 stepStates)을 받아, 매니저가 고른 상대 수비 방식대로 수비 5명(x1~x5)의 위치를 단계마다 정한다.
 * 규칙이 정하는 것이지 경기 기록에서 추정하는 것이 아니다 — "상대가 이렇게 막으면 이렇게 움직인다" 를 보여 주는 용도다.
 *
 * 맨투맨   수비 i 는 처음에 공격 i 번을 막는다. 자기 사람과 림 사이(골 쪽)에 서고, 공을 가진 사람에게는 붙고,
 *          공에서 멀수록 페인트 쪽으로 처져서 돕는다.
 * 지역     2-3 지역 수비. 다섯 자리(앞줄 둘 · 뒷줄 셋)가 공 쪽으로 쏠리고, 공에 가장 가까운 수비가 달려 나간다.
 *          공 없이 페인트에 들어온 공격수는 가까운 수비가 따라붙는다.
 * 스크린   스크린과 핸드오프(건네주는 사람이 스크리너 역할)를 만나면
 *          스위치  두 수비가 마크를 맞바꾼다 (맨투맨은 그 뒤로 계속, 지역은 자기 자리 기준이라 그 단계만)
 *          스테이  스크린에 걸린 수비가 스크린을 돌아 자기 사람(자리)을 계속 따라간다 — 한 박자 늦게 움직인다.
 *                 맨투맨이면 스크리너의 수비가 잠깐 튀어나와 도운 뒤(헤지) 자기 사람에게 돌아간다
 *
 * 좌표는 공격과 같은 0~1 (x 사이드라인, y 베이스라인 → 하프라인). 거리는 미터로 바꿔 잰다.
 */
import type { CourtPoint, Play } from '../api/types'
import { COURT_H, COURT_W, RIM_X, RIM_Y } from './court'
import type { StepState } from './tactics'

export type DefenseKind = 'man' | 'zone'
export type ScreenCall = 'switch' | 'stay'
export interface DefenseScheme { kind: DefenseKind; screen: ScreenCall }

export const DEFENSE_KIND_LABEL: Record<DefenseKind, string> = { man: '맨투맨 수비', zone: '지역 수비 (2-3)' }
export const SCREEN_CALL_LABEL: Record<ScreenCall, string> = { switch: '스위치', stay: '스테이' }

/** 한 단계 안에서 수비가 스크린에 반응한 일 */
export interface ScreenEvent {
  kind: ScreenCall
  at: CourtPoint // 스크린을 선 자리
  chaser: number // 스크린에 걸린 수비 (0부터)
  helper: number | null // 스크리너를 막던 수비 (지역 수비에서 스위치를 받는 옆 수비)
}

export interface DefenseSim {
  scheme: DefenseScheme
  pos: CourtPoint[][] // pos[k][i] = k단계까지 끝난 뒤 수비 i 위치 (길이 = 단계 수 + 1)
  guards: (number | null)[][] // guards[k][i] = 그때 수비 i 가 막는 공격 슬롯 (1~5). 지역 수비는 가장 가까운 공격수
  events: ScreenEvent[][] // events[k] = k+1 단계(0부터 k)에서 일어난 스크린 대응
  notes: string[] // notes[k] = k 단계 재생 때 보여 줄 수비 설명 한 줄 (없으면 빈 문자열)
}

const M = (p: CourtPoint): [number, number] => [p.x * COURT_W, p.y * COURT_H]
const N = (x: number, y: number): CourtPoint => ({ x: x / COURT_W, y: y / COURT_H })
const dist = (a: CourtPoint, b: CourtPoint) => { const [ax, ay] = M(a), [bx, by] = M(b); return Math.hypot(ax - bx, ay - by) }
const clampPt = (p: CourtPoint): CourtPoint => ({ x: Math.min(0.97, Math.max(0.03, p.x)), y: Math.min(0.96, Math.max(0.03, p.y)) })
const RIM_PT: CourtPoint = N(RIM_X, RIM_Y)

// "x1이 · x2가" — 숫자는 읽는 소리(일·이·삼·사·오)의 받침으로 조사를 고른다
const HAS_FINAL = [false, true, false, true, false, false] // 인덱스 = 수비 번호 (1 일 · 3 삼 만 받침)
const xi = (i: number) => `x${i + 1}${HAS_FINAL[i + 1] ? '이' : '가'}`
const xn = (i: number) => `x${i + 1}${HAS_FINAL[i + 1] ? '은' : '는'}`

/** 공격수 P 를 막는 자리 — P 와 림 사이. 공을 가졌으면 1m, 아니면 공과 멀수록 더 처지고 공 쪽으로 조금 기운다 (헬프) */
export function guardSpot(p: CourtPoint, ball: CourtPoint | null, hasBall: boolean): CourtPoint {
  const [px, py] = M(p), [rx, ry] = [RIM_X, RIM_Y]
  const d = Math.hypot(rx - px, ry - py)
  if (d < 0.05) return clampPt(p)
  let gap = hasBall || !ball ? 1.0 : 1.2 + 1.6 * Math.min(1, dist(p, ball) / 9)
  gap = Math.min(gap, d * (d < 1.5 ? 0.4 : 0.6))
  let x = px + ((rx - px) / d) * gap
  let y = py + ((ry - py) / d) * gap
  if (!hasBall && ball) {
    const [bx, by] = M(ball)
    const hx = (bx - x) * 0.15, hy = (by - y) * 0.15
    const h = Math.hypot(hx, hy)
    const k = h > 1.2 ? 1.2 / h : 1
    x += hx * k; y += hy * k
  }
  return clampPt(N(x, y))
}

// 2-3 지역 수비의 기본 자리: x1·x2 앞줄, x3·x4 뒷줄 양쪽, x5 골밑
const ZONE_HOME: CourtPoint[] = [
  { x: 0.37, y: 0.44 }, { x: 0.63, y: 0.44 }, { x: 0.2, y: 0.2 }, { x: 0.8, y: 0.2 }, { x: 0.5, y: 0.13 },
]

const isPaint = (p: CourtPoint) => { const [x, y] = M(p); return Math.abs(x - RIM_X) <= 2.45 && y <= 5.8 && y >= 0 }

/** 지역 수비 한 순간의 자리 */
function zoneSpots(off: CourtPoint[], holder: number | null): CourtPoint[] {
  const ball = holder ? off[holder - 1] : RIM_PT
  const sx = (ball.x - 0.5) * 0.35
  const sy = Math.max(-0.05, Math.min(0.05, (ball.y - 0.5) * 0.12))
  const pos = ZONE_HOME.map((h, i) => clampPt({ x: h.x + (i === 4 ? sx * 0.5 : sx), y: h.y + sy }))
  if (holder === null) return pos
  const taken = new Set<number>()
  // 공에 가장 가까운 수비가 달려 나간다 (공이 코트 밖이면 — 인바운드 — 안쪽에서 기다린다)
  const out = pos.map((p, i) => [dist(p, ball), i] as const).sort((a, b) => a[0] - b[0])[0][1]
  if (ball.y >= 0) pos[out] = guardSpot(ball, ball, true)
  taken.add(out)
  // 공 없이 페인트에 들어온 공격수는 가까운 수비가 반쯤 따라붙는다
  off.forEach((p, s) => {
    if (s + 1 === holder || !isPaint(p)) return
    const near = pos.map((q, i) => [dist(q, p), i] as const).filter(([, i]) => !taken.has(i)).sort((a, b) => a[0] - b[0])[0]
    if (!near) return
    const g = guardSpot(p, ball, false)
    pos[near[1]] = { x: (pos[near[1]].x + g.x) / 2, y: (pos[near[1]].y + g.y) / 2 }
    taken.add(near[1])
  })
  return pos
}

const nearest = (pts: CourtPoint[], p: CourtPoint, skip = new Set<number>()) =>
  pts.map((q, i) => [dist(q, p), i] as const).filter(([, i]) => !skip.has(i)).sort((a, b) => a[0] - b[0])[0]?.[1] ?? 0

/** 스크린(또는 핸드오프)을 받는 쪽 · 거는 쪽 · 서는 자리 */
function screensOf(play: Play, k: number, from: StepState, to: StepState): { screener: number; target: number; at: CourtPoint }[] {
  return play.steps[k].actions.flatMap((a) => {
    if (a.type === 'screen' && a.target && a.to) return [{ screener: a.slot, target: a.target, at: a.to }]
    if (a.type === 'handoff' && a.target) return [{ screener: a.slot, target: a.target, at: from.pos[a.slot - 1] ?? to.pos[a.slot - 1] }]
    return []
  })
}

export function simulateDefense(play: Play, states: StepState[], scheme: DefenseScheme): DefenseSim {
  const n = play.steps.length
  const pos: CourtPoint[][] = []
  const guards: (number | null)[][] = []
  const events: ScreenEvent[][] = []
  const notes: string[] = []
  const spotsAt = (st: StepState, assign: number[]) => {
    if (scheme.kind === 'zone') return zoneSpots(st.pos, st.holder)
    const ball = st.holder ? st.pos[st.holder - 1] : null
    return assign.map((slot) => guardSpot(st.pos[slot - 1], ball, slot === st.holder))
  }
  const guardsAt = (st: StepState, assign: number[], spots: CourtPoint[]) =>
    scheme.kind === 'man' ? [...assign] : spots.map((q) => nearest(st.pos, q) + 1)

  let assign = [1, 2, 3, 4, 5] // 맨투맨: 수비 i 가 막는 공격 슬롯
  pos.push(spotsAt(states[0], assign))
  guards.push(guardsAt(states[0], assign, pos[0]))
  for (let k = 0; k < n; k++) {
    const from = states[k], to = states[k + 1]
    const evs: ScreenEvent[] = []
    const lines: string[] = []
    const next = [...assign]
    for (const sc of screensOf(play, k, from, to)) {
      if (scheme.kind === 'man') {
        const chaser = next.indexOf(sc.target), helper = next.indexOf(sc.screener)
        if (chaser < 0 || helper < 0) continue
        if (scheme.screen === 'switch') {
          next[chaser] = sc.screener
          next[helper] = sc.target
          lines.push(`x${chaser + 1}·x${helper + 1} 스위치 — ${xi(helper)} ${sc.target}번, ${xi(chaser)} ${sc.screener}번을 막아요`)
        } else {
          lines.push(`${xn(chaser)} 스크린을 돌아 ${sc.target}번을 계속 따라가고, ${xn(helper)} 잠깐 도운 뒤 ${sc.screener}번에게 돌아가요`)
        }
        evs.push({ kind: scheme.screen, at: sc.at, chaser, helper })
      } else {
        // 지역 수비: 스크린이 서는 자리에 가장 가까운 수비가 걸린 수비다
        const chaser = nearest(pos[k], sc.at)
        const helper = nearest(pos[k], sc.at, new Set([chaser]))
        lines.push(scheme.screen === 'switch'
          ? `지역 수비 스위치 — ${xn(chaser)} 자리를 지키고 ${sc.target}번은 ${xi(helper)} 넘겨받아요`
          : `${xi(chaser)} 스크린을 돌아 자기 자리로 돌아가요 (한 박자 늦어요)`)
        evs.push({ kind: scheme.screen, at: sc.at, chaser, helper: scheme.screen === 'switch' ? helper : null })
      }
    }
    assign = next
    const spots = spotsAt(to, assign)
    pos.push(spots)
    guards.push(guardsAt(to, assign, spots))
    events.push(evs)
    notes.push(lines.join(' · '))
  }
  return { scheme, pos, guards, events, notes }
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const bezier = (a: CourtPoint, c: CourtPoint, b: CourtPoint, t: number): CourtPoint => ({
  x: (1 - t) ** 2 * a.x + 2 * (1 - t) * t * c.x + t * t * b.x,
  y: (1 - t) ** 2 * a.y + 2 * (1 - t) * t * c.y + t * t * b.y,
})

/** 스크린 바깥쪽(림 반대편)으로 돌아가는 곡선의 조절점 */
function aroundPoint(at: CourtPoint, from: CourtPoint, to: CourtPoint): CourtPoint {
  const [ax, ay] = M(at)
  const [rx, ry] = [ax - RIM_X, ay - RIM_Y]
  const r = Math.hypot(rx, ry) || 1
  const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
  // 스크린 자리에서 림 반대쪽으로 1.2m 밀어 낸 점을 거쳐 가게 (중간점과 섞어 너무 크게 돌지 않게)
  const over = N(ax + (rx / r) * 1.2, ay + (ry / r) * 1.2)
  return { x: over.x * 0.7 + mid.x * 0.3, y: over.y * 0.7 + mid.y * 0.3 }
}

/** cursor(0 ~ 단계 수) 위치의 수비 5명. 스테이면 걸린 수비가 늦게 돌아가고, 맨투맨 스크리너 수비는 튀어나왔다 돌아온다 */
export function defenseFrameAt(sim: DefenseSim, cursor: number): CourtPoint[] {
  const n = sim.pos.length - 1
  const c = Math.min(Math.max(cursor, 0), n)
  if (c === 0 || n === 0) return sim.pos[0]
  const k = Math.min(Math.floor(c), n - 1)
  const raw = c - k
  const t = ease(raw)
  const from = sim.pos[k], to = sim.pos[k + 1]
  return from.map((p, i) => {
    const ev = sim.events[k].find((e) => e.chaser === i || e.helper === i)
    if (ev && ev.kind === 'stay' && ev.chaser === i) {
      const late = ease(Math.min(1, Math.max(0, (raw - 0.3) / 0.7)))
      return bezier(p, aroundPoint(ev.at, p, to[i]), to[i], late)
    }
    if (ev && ev.kind === 'stay' && ev.helper === i && sim.scheme.kind === 'man') {
      const hedge = { x: ev.at.x + (ev.at.x - p.x) * 0.3, y: ev.at.y + (ev.at.y - p.y) * 0.3 }
      return bezier(p, hedge, to[i], t)
    }
    return { x: p.x + (to[i].x - p.x) * t, y: p.y + (to[i].y - p.y) * t }
  })
}
