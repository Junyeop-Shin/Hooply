/**
 * 전술판 (S-29, docs/07 FR-47) — 하프코트 위에 공격 5명과 공을 그리고 단계별로 재생한다.
 *
 * 좌표는 0~1 → SVG viewBox 150×140 (1칸 = 10cm). 베이스라인이 위, 하프라인이 아래다.
 * 멈춰 있을 때는 "다음에 할 단계" 의 화살표를, 재생 중에는 지금 단계의 화살표를 그린다.
 * 전술이 바뀌면 부모가 key 를 바꿔 처음부터 다시 그린다.
 * 애니메이션은 라이브러리 없이 requestAnimationFrame 으로 보간한다. 움직임 줄이기 설정이면 단계만 바뀐다.
 */
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react'
import type { CourtPoint, Play, PlayAction } from '../api/types'
import { RIM, frameAt, shownStep, stepStates, zigzag } from '../lib/tactics'

const W = 150, H = 140
const R = 5.6 // 선수 동그라미 반지름
const STEP_MS = 1300 // 1× 에서 한 단계 재생 시간
const HOLD_MS = 450 // 연속 재생 때 단계 사이 멈춤
const SPEEDS = [1, 2, 0.5] as const
const OOB_H = 13 // 코트 밖 띠 높이 (베이스라인 뒤 약 1.3m)

export type BoardTone = 'black' | 'white' | 'neutral'

const TONE: Record<BoardTone, { fill: string; ink: string; stroke: string }> = {
  black: { fill: 'var(--color-team-black)', ink: 'var(--color-team-black-ink)', stroke: 'var(--color-team-black-sub)' },
  white: { fill: 'var(--color-team-white)', ink: 'var(--color-team-white-ink)', stroke: 'var(--color-team-white-ink)' },
  neutral: { fill: 'var(--color-inverse)', ink: 'var(--color-on-inverse)', stroke: 'var(--color-on-inverse)' },
}

const sx = (p: CourtPoint) => p.x * W
const sy = (p: CourtPoint) => p.y * H

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mq) return
    const on = () => setReduced(mq.matches)
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  return reduced
}

export function TacticBoard({
  play, tone = 'neutral', names, onSlotTap,
}: {
  play: Play
  tone?: BoardTone
  names?: (string | null)[] // names[i] = 슬롯 i+1 에 앉힌 선수 이름
  onSlotTap?: (slot: number) => void
}) {
  const n = play.steps.length
  const states = useMemo(() => stepStates(play), [play])
  // 인바운드처럼 베이스라인 뒤(y<0)에 서는 사람이 있으면 위쪽에 코트 밖 띠를 붙인다
  const oob = useMemo(() => [...play.start, ...play.steps.flatMap((s) => s.actions.flatMap((a) => (a.to ? [a.to] : [])))].some((p) => p.y < 0), [play])
  const top = oob ? OOB_H : 0
  const reduced = useReducedMotion()
  const [cursor, setCursorState] = useState(0)
  const cursorRef = useRef(0)
  const [target, setTarget] = useState<number | null>(null) // 재생 중이면 도착할 cursor
  const [speedIdx, setSpeedIdx] = useState(0)
  const speed = SPEEDS[speedIdx]
  const ids = useId().replace(/:/g, '')

  const setCursor = (c: number) => { cursorRef.current = c; setCursorState(c) }

  useEffect(() => {
    if (target === null) return
    let raf = 0
    let last = performance.now()
    let hold = 0
    let c = cursorRef.current
    const tick = (now: number) => {
      // rAF 가 주는 시각은 그 프레임의 시작 시각이라 effect 에서 잰 시각보다 이를 수 있다 — 음수면 재생 위치가 뒤로 가서 단계가 -1 이 된다
      const dt = Math.max(0, now - last)
      last = now
      if (hold > 0) { hold -= dt; raf = requestAnimationFrame(tick); return }
      if (reduced) {
        c = Math.min(Math.floor(c) + 1, target)
        hold = (STEP_MS + HOLD_MS) / speed
      } else {
        const next = c + (dt * speed) / STEP_MS
        const boundary = Math.floor(c) + 1
        if (next >= boundary && boundary < target) { c = boundary; hold = HOLD_MS / speed } else c = Math.min(next, target)
      }
      cursorRef.current = c
      setCursorState(c)
      if (c >= target) { setTarget(null); return }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, speed, reduced])

  const playing = target !== null
  const atEnd = cursor >= n
  const frame = frameAt(play, states, cursor)
  const k = shownStep(play, cursor)
  const colors = TONE[tone]

  const toStart = () => { setTarget(null); setCursor(0) }
  const prev = () => { setTarget(null); setCursor(Math.max(0, Math.ceil(cursor) - 1)) }
  const next = () => { if (!atEnd) setTarget(Math.min(Math.floor(cursor) + 1, n)) }
  const toggle = () => {
    if (playing) { setTarget(null); return }
    if (atEnd) setCursor(0)
    setTarget(n)
  }

  return (
    <div className="space-y-2">
      <svg viewBox={`0 ${-top} ${W} ${H + top}`} className="w-full touch-manipulation select-none rounded-2xl" role="img" aria-label={`${play.name} 전술판`}>
        <defs>
          <marker id={`ah-${ids}`} viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
            <path d="M0,0 L6,3 L0,6 z" style={{ fill: 'var(--color-ink)' }} />
          </marker>
          <marker id={`ahb-${ids}`} viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
            <path d="M0,0 L6,3 L0,6 z" style={{ fill: 'var(--color-brand-ink)' }} />
          </marker>
        </defs>
        {oob && (
          <g>
            <rect x={0} y={-top} width={W} height={top} style={{ fill: 'var(--color-sunken)' }} />
            <text x={4} y={-top + 7} fontSize={4.2} style={{ fill: 'var(--color-muted)' }}>코트 밖 (베이스라인 뒤)</text>
          </g>
        )}
        <Court />
        {k !== null && play.steps[k] && (
          <g opacity={playing ? 0.35 : 0.85}>
            {play.steps[k].actions.map((a, i) => (
              <ActionMark key={i} a={a} from={states[k].pos} to={states[k + 1].pos} arrow={`url(#ah-${ids})`} brandArrow={`url(#ahb-${ids})`} />
            ))}
          </g>
        )}
        {frame.pos.map((p, i) => {
          const name = names?.[i]
          const below = sy(p) + R + 5.2 < H - 1
          return (
            <g
              key={i}
              onClick={onSlotTap ? () => onSlotTap(i + 1) : undefined}
              role={onSlotTap ? 'button' : undefined}
              aria-label={onSlotTap ? `${i + 1}번 자리 선수 고르기` : undefined}
              className={onSlotTap ? 'cursor-pointer' : undefined}
            >
              {onSlotTap && <circle cx={sx(p)} cy={sy(p)} r={R + 4} fill="transparent" />}
              <circle cx={sx(p)} cy={sy(p)} r={R} style={{ fill: colors.fill, stroke: colors.stroke }} strokeWidth={0.6} />
              <text x={sx(p)} y={sy(p) + 1.9} textAnchor="middle" fontSize={5.4} fontWeight={800} style={{ fill: colors.ink }}>{i + 1}</text>
              {name && (
                <text
                  x={sx(p)} y={below ? sy(p) + R + 4.6 : sy(p) - R - 1.8} textAnchor="middle" fontSize={4.1} fontWeight={700}
                  style={{ fill: 'var(--color-ink)', stroke: 'var(--color-brand-soft)', paintOrder: 'stroke' }} strokeWidth={1.4}
                >
                  {name.length > 5 ? `${name.slice(0, 5)}…` : name}
                </text>
              )}
            </g>
          )
        })}
        <circle
          cx={sx(frame.ball) + 4 * frame.ballOffset} cy={sy(frame.ball) + 3.4 * frame.ballOffset} r={2.3}
          style={{ fill: 'var(--color-court-500)' }} stroke="#7c2d12" strokeWidth={0.5}
        />
      </svg>

      <p className="min-h-10 text-sm text-ink" aria-live="polite">
        {k === null || !play.steps[k] ? (
          <span className="text-muted">끝났어요 — ▶ 을 누르면 처음부터 다시 재생해요</span>
        ) : (
          <><span className="mr-1.5 font-bold text-brand-ink">{k + 1}/{n}</span>{play.steps[k].caption}</>
        )}
      </p>

      <div className="flex items-center justify-between gap-1">
        <CtrlButton label="처음" onClick={toStart} disabled={cursor === 0 && !playing}><Icon d="M6 5v14M19 5 9 12l10 7z" /></CtrlButton>
        <CtrlButton label="이전 단계" onClick={prev} disabled={cursor === 0}><Icon d="M17 5 7 12l10 7z" /></CtrlButton>
        <CtrlButton label={playing ? '일시정지' : '재생'} onClick={toggle} primary>
          {playing ? <Icon d="M8 5v14M16 5v14" /> : <Icon d="M7 5l12 7-12 7z" />}
        </CtrlButton>
        <CtrlButton label="다음 단계" onClick={next} disabled={atEnd || playing}><Icon d="M5 5l10 7-10 7zM18 5v14" /></CtrlButton>
        <button
          type="button" onClick={() => setSpeedIdx((speedIdx + 1) % SPEEDS.length)} aria-label={`재생 속도 ${speed}배`}
          className="min-h-11 min-w-14 rounded-xl border border-line bg-surface px-2 text-sm font-bold text-ink-2 active:bg-sunken"
        >
          {speed}×
        </button>
      </div>
      <Legend />
    </div>
  )
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

function CtrlButton({ label, onClick, disabled, primary, children }: { label: string; onClick: () => void; disabled?: boolean; primary?: boolean; children: ReactNode }) {
  return (
    <button
      type="button" onClick={onClick} disabled={disabled} aria-label={label}
      className={`flex min-h-11 flex-1 items-center justify-center rounded-xl text-base font-bold transition disabled:opacity-35 ${
        primary ? 'bg-brand text-on-brand' : 'border border-line bg-surface text-ink active:bg-sunken'
      }`}
    >
      {children}
    </button>
  )
}

/** 하프코트 (FIBA). 라인은 반투명 오렌지 글자색이라 밝은·어두운 모드 모두에서 보인다 */
function Court() {
  const line = { stroke: 'var(--color-brand-ink)', strokeOpacity: 0.45, strokeWidth: 0.7, fill: 'none' }
  return (
    <g>
      <rect x={0} y={0} width={W} height={H} rx={4} style={{ fill: 'var(--color-brand-soft)' }} />
      <rect x={0.35} y={0.35} width={W - 0.7} height={H - 0.7} rx={3.8} style={line} />
      <rect x={50.5} y={0} width={49} height={58} style={line} />
      <path d="M57,58 A18,18 0 0 0 93,58" style={line} />
      <path d="M57,58 A18,18 0 0 1 93,58" style={line} strokeDasharray="2 2" />
      <path d="M9,0 L9,29.9 A67.5,67.5 0 0 0 141,29.9 L141,0" style={line} />
      <path d="M62.5,15.75 A12.5,12.5 0 0 0 87.5,15.75" style={line} />
      <line x1={66} y1={12} x2={84} y2={12} style={{ ...line, strokeOpacity: 0.8, strokeWidth: 1 }} />
      <circle cx={75} cy={15.75} r={2.25} style={{ fill: 'none', stroke: 'var(--color-court-500)', strokeWidth: 0.8 }} />
      <path d={`M57,${H} A18,18 0 0 1 93,${H}`} style={line} />
    </g>
  )
}

/** 원 가장자리에서 시작·끝나도록 선을 줄인다 */
function trim(x1: number, y1: number, x2: number, y2: number, a: number, b: number): [number, number, number, number] | null {
  const len = Math.hypot(x2 - x1, y2 - y1)
  if (len <= a + b + 0.5) return null
  const ux = (x2 - x1) / len, uy = (y2 - y1) / len
  return [x1 + ux * a, y1 + uy * a, x2 - ux * b, y2 - uy * b]
}

function ActionMark({ a, from, to, arrow, brandArrow }: { a: PlayAction; from: CourtPoint[]; to: CourtPoint[]; arrow: string; brandArrow: string }) {
  const p = from[a.slot - 1]
  const ink = { stroke: 'var(--color-ink)', fill: 'none' }
  if ((a.type === 'move' || a.type === 'cut' || a.type === 'dribble') && a.to) {
    const seg = trim(sx(p), sy(p), sx(a.to), sy(a.to), R + 0.6, 0.5)
    if (!seg) return null
    const [x1, y1, x2, y2] = seg
    if (a.type === 'dribble') return <path d={zigzag(x1, y1, x2, y2)} style={ink} strokeWidth={0.8} markerEnd={arrow} />
    return <line x1={x1} y1={y1} x2={x2} y2={y2} style={ink} strokeWidth={a.type === 'cut' ? 1.7 : 0.8} markerEnd={arrow} />
  }
  if (a.type === 'screen' && a.to && a.target) {
    const tx = sx(a.to), ty = sy(a.to)
    const seg = trim(sx(p), sy(p), tx, ty, R + 0.6, 0)
    // T 막대 방향: 스크리너가 움직인 방향에 수직. 거의 제자리면 받는 동료 쪽 방향에 수직
    const mate = from[a.target - 1]
    let dx = tx - sx(p), dy = ty - sy(p)
    if (Math.hypot(dx, dy) < 3) { dx = sx(mate) - tx; dy = sy(mate) - ty }
    const len = Math.hypot(dx, dy) || 1
    const nx = (-dy / len) * 3.8, ny = (dx / len) * 3.8
    return (
      <g style={ink}>
        {seg && <line x1={seg[0]} y1={seg[1]} x2={seg[2]} y2={seg[3]} strokeWidth={0.8} />}
        <line x1={tx - nx} y1={ty - ny} x2={tx + nx} y2={ty + ny} strokeWidth={1.8} strokeLinecap="round" />
      </g>
    )
  }
  if ((a.type === 'pass' || a.type === 'handoff') && a.target) {
    const q = to[a.target - 1]
    const seg = trim(sx(p), sy(p), sx(q), sy(q), R + 0.6, R + 1)
    if (!seg) return null
    return <line x1={seg[0]} y1={seg[1]} x2={seg[2]} y2={seg[3]} style={ink} strokeWidth={0.8} strokeDasharray={a.type === 'pass' ? '2.2 1.6' : '0.9 1.2'} markerEnd={arrow} />
  }
  if (a.type === 'shot') {
    const seg = trim(sx(p), sy(p), sx(RIM), sy(RIM), R + 0.6, 2.8)
    if (!seg) return null
    return <line x1={seg[0]} y1={seg[1]} x2={seg[2]} y2={seg[3]} style={{ stroke: 'var(--color-brand-ink)' }} strokeWidth={1} strokeDasharray="2.2 1.6" markerEnd={brandArrow} />
  }
  return null
}

/** 범례 한 줄 — 전술판과 같은 선 모양 */
function Legend() {
  const ink = { stroke: 'var(--color-ink)', fill: 'none' }
  const items: [string, ReactNode][] = [
    ['이동', <line key="m" x1={1} y1={4} x2={19} y2={4} style={ink} strokeWidth={1} />],
    ['컷', <line key="c" x1={1} y1={4} x2={19} y2={4} style={ink} strokeWidth={2.2} />],
    ['드리블', <path key="d" d={zigzag(1, 4, 19, 4, 1.8, 3.5)} style={ink} strokeWidth={1} />],
    ['패스', <line key="p" x1={1} y1={4} x2={19} y2={4} style={ink} strokeWidth={1} strokeDasharray="3 2" />],
    ['스크린', <g key="s" style={ink}><line x1={1} y1={4} x2={17} y2={4} strokeWidth={1} /><line x1={17} y1={0.5} x2={17} y2={7.5} strokeWidth={2.2} /></g>],
  ]
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-muted" aria-label="범례">
      {items.map(([label, icon]) => (
        <span key={label} className="inline-flex items-center gap-1">
          <svg viewBox="0 0 20 8" className="h-2 w-5" aria-hidden="true">{icon}</svg>{label}
        </span>
      ))}
    </div>
  )
}
