/**
 * 스포트라이트 — 화면을 어둡게 덮고 지금 할 칸만 밝게 뚫어 보여 준다 (시작 안내용).
 *
 * - 대상은 `data-tutorial="<key>"` 가 붙은 요소. 여러 개면 구멍도 여러 개 (예: 입력칸 + 아래 버튼)
 * - 덮개는 누르는 것을 막지 않는다(pointer-events none). 안내 때문에 앱을 못 쓰게 되지 않도록
 * - 밝은 칸을 누르거나 "알겠어요"·Esc 를 누르면 사라진다. 대상이 4초 안에 안 나타나면 아무것도 그리지 않는다
 * - 스크롤·크기 변화를 따라가려고 떠 있는 동안만 매 프레임 위치를 읽는다 (바뀔 때만 다시 그림)
 */
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Box = { x: number; y: number; w: number; h: number }
const PAD = 6
const sameBoxes = (a: Box[] | null, b: Box[]) => !!a && a.length === b.length && a.every((r, i) => Math.abs(r.x - b[i].x) < 0.5 && Math.abs(r.y - b[i].y) < 0.5 && Math.abs(r.w - b[i].w) < 0.5 && Math.abs(r.h - b[i].h) < 0.5)

export function Spotlight({ target, title, text, onClose }: { target: string; title: string; text: string; onClose: () => void }) {
  const [boxes, setBoxes] = useState<Box[] | null>(null)
  const closeRef = useRef(onClose)
  useEffect(() => { closeRef.current = onClose }, [onClose])

  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const sel = `[data-tutorial="${target}"]`
    const started = performance.now()
    let raf = 0
    let scrolled = false
    const tick = () => {
      const els = Array.from(document.querySelectorAll<HTMLElement>(sel))
      if (els.length) {
        if (!scrolled) { els[0].scrollIntoView({ block: 'center', behavior: reduce ? 'auto' : 'smooth' }); scrolled = true }
        const next = els.map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0 && r.height > 0)
          .map((r) => ({ x: r.left - PAD, y: r.top - PAD, w: r.width + PAD * 2, h: r.height + PAD * 2 }))
        setBoxes((prev) => (sameBoxes(prev, next) ? prev : next))
      } else if (performance.now() - started > 4000) {
        setBoxes([])
        return
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    // 밝은 칸을 누르면(= 안내대로 행동하면) 사라진다. 누른 동작 자체는 그대로 전달된다
    const onDown = (e: PointerEvent) => { if ((e.target as Element | null)?.closest?.(sel)) closeRef.current() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeRef.current() }
    document.addEventListener('pointerdown', onDown, true)
    document.addEventListener('keydown', onKey)
    return () => { cancelAnimationFrame(raf); document.removeEventListener('pointerdown', onDown, true); document.removeEventListener('keydown', onKey) }
  }, [target])

  if (!boxes || boxes.length === 0) return null
  const vw = window.innerWidth
  const vh = window.innerHeight
  const top = Math.min(...boxes.map((b) => b.y))
  // 말풍선은 첫 칸 바로 아래. 아래 공간이 모자라면 위로
  const first = boxes[0]
  const below = vh - (first.y + first.h) > 170
  const width = Math.min(360, vw - 32)
  const left = Math.max(16, Math.min(vw - width - 16, first.x + first.w / 2 - width / 2))
  const tipStyle = below ? { top: first.y + first.h + 12, left, width } : { bottom: Math.max(16, vh - (boxes.length > 1 ? top : first.y) + 12), left, width }

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-40">
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <defs>
          <mask id="hooply-spotlight-mask">
            <rect width="100%" height="100%" fill="white" />
            {boxes.map((b, i) => <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h} rx="16" fill="black" />)}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgba(11,18,32,0.62)" mask="url(#hooply-spotlight-mask)" />
        {boxes.map((b, i) => <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h} rx="16" fill="none" stroke="#f26b1d" strokeWidth="2.5" className="motion-safe:animate-pulse" />)}
      </svg>
      <div role="dialog" aria-label={title} className="pointer-events-auto absolute rounded-2xl bg-surface p-4 shadow-xl" style={tipStyle}>
        <p className="text-xs font-bold text-brand-ink">시작 안내</p>
        <p className="mt-0.5 font-bold text-ink">{title}</p>
        <p className="mt-1 text-sm leading-relaxed text-ink-2">{text}</p>
        <div className="mt-3 flex justify-end">
          <button type="button" onClick={() => closeRef.current()} className="min-h-9 rounded-lg bg-brand px-4 text-sm font-semibold text-on-brand">알겠어요</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
