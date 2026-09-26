/**
 * 배지 아이콘 = 틀(잠김·단일·동·은·금) + 그림(12종). 조각은 badge-art.ts(자동 생성)에 있고, 여기서는 조합만 한다.
 * 그라데이션은 모든 배지가 공유하므로 화면에 <BadgeDefs /> 를 한 번 그려 둔다. 규칙은 docs/06-배지.md.
 */
import { BADGE_DEFS, FRAMES, PICT_SHIFT, PICTS, type BadgeFrame, type BadgePict } from './badge-art'

export function BadgeDefs() {
  return <svg width="0" height="0" className="absolute" aria-hidden="true" focusable="false"><defs dangerouslySetInnerHTML={{ __html: BADGE_DEFS }} /></svg>
}

export function BadgeIcon({ frame, pict, label, className = 'w-10' }: { frame: BadgeFrame; pict: BadgePict; label: string; className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={`block h-auto overflow-visible ${className}`} role="img" aria-label={label}>
      <g dangerouslySetInnerHTML={{ __html: FRAMES[frame] }} />
      <g
        transform={`translate(0 ${PICT_SHIFT})`}
        style={frame === 'locked' ? { filter: 'grayscale(1)', opacity: 0.42 } : undefined}
        dangerouslySetInnerHTML={{ __html: PICTS[pict] }}
      />
    </svg>
  )
}
