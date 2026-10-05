/**
 * 화면에 하나뿐인 로딩 표시.
 * 섹션마다 놓인 <Spinner /> 는 "지금 불러오는 중" 이라고 알리기만 하고(자리만 차지), 실제 빙글빙글은 여기서 화면 전체를 흐리게 덮고 가운데에 하나만 그린다.
 * 섹션이 여럿인 화면(홈 · 팀)에서 로딩 표시와 기다림 문구가 섹션 수만큼 겹쳐 보이지 않게 하려는 것이다.
 * 5초가 넘게 돌면 서버가 깨는 중일 수 있어 농구 문구를 무작위로 띄우고 6초마다 바꾼다 (lib/wait-messages).
 */
import { useEffect, useState } from 'react'
import { useIsLoading } from '../store/loading'
import { pickWaitMessage, ROTATE_MS, SLOW_AFTER_MS, WAIT_SUBLINE } from '../lib/wait-messages'

/** 로딩이 이어지는 동안의 기다림 문구. 5초 전에는 null */
function useSlowMessage(active: boolean): string | null {
  const [msg, setMsg] = useState<string | null>(null)
  useEffect(() => {
    if (!active) return
    let rotate: number | undefined
    const start = window.setTimeout(() => {
      setMsg(pickWaitMessage())
      rotate = window.setInterval(() => setMsg((m) => pickWaitMessage(m)), ROTATE_MS)
    }, SLOW_AFTER_MS)
    return () => { window.clearTimeout(start); if (rotate !== undefined) window.clearInterval(rotate); setMsg(null) }
  }, [active])
  return msg
}

export function LoadingHost() {
  const active = useIsLoading()
  const slow = useSlowMessage(active)
  if (!active) return null
  // 화면 전체를 살짝 흐리게 덮는다. 0.15초 뒤에 나타나므로 금방 끝나는 로딩에서는 번쩍이지 않는다. 터치는 막지 않는다(뒤로 가기는 눌린다)
  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex animate-[loading-in_200ms_ease-out_150ms_both] flex-col items-center justify-center gap-3 bg-canvas/70 px-6 backdrop-blur-[3px]">
      <span className="size-8 animate-spin rounded-full border-[3px] border-brand-line border-t-brand" aria-hidden={slow ? true : undefined} />
      {slow && (
        <div role="status" aria-live="polite" className="text-center">
          <p className="text-sm font-semibold text-ink">{slow}</p>
          <p className="mt-0.5 text-xs text-ink-2">{WAIT_SUBLINE}</p>
        </div>
      )}
    </div>
  )
}
