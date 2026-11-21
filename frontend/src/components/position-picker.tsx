/** 포지션을 선호 순서대로 고르는 칩 — 누른 순서가 번호가 되고, 다시 누르면 빠진다 (프로필 · 매니저의 회원 포지션 수정). */
import { POSITIONS, type Position } from '../api/types'

export function PositionPicker({ value, onChange }: { value: Position[]; onChange: (next: Position[]) => void }) {
  return (
    <div className="flex gap-1.5">
      {POSITIONS.map((pos) => {
        const idx = value.indexOf(pos)
        return (
          <button key={pos} type="button" onClick={() => onChange(idx >= 0 ? value.filter((x) => x !== pos) : [...value, pos])}
            aria-pressed={idx >= 0}
            className={`relative min-h-11 flex-1 rounded-lg border text-sm font-bold ${idx >= 0 ? 'border-inverse bg-inverse text-on-inverse' : 'border-line bg-surface text-ink'}`}>
            {idx >= 0 && <span className="absolute -left-1 -top-1.5 flex size-5 items-center justify-center rounded-full bg-brand text-[11px] text-on-brand">{idx + 1}</span>}
            {pos}
          </button>
        )
      })}
    </div>
  )
}
