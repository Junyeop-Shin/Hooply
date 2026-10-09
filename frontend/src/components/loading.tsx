/**
 * 화면 전체를 덮는 로딩 표시 — 두 층 중 "화면 전체" 쪽 (store/loading).
 *   <Spinner page />  화면이 통째로 비어 있을 때. 0.15초 뒤 화면을 살짝 흐리게 덮고 가운데에 링 하나
 *   <Spinner />       섹션 하나만 불러올 때. 그 자리에 작은 링만 그리고(ui.tsx) 여기서는 아무것도 덮지 않는다 —
 *                     이미 보이는 내용이 흐려지지 않게
 * 어느 쪽이든 5초(SLOW_AFTER_MS)를 넘게 이어지면 서버가 깨는 중일 수 있어, 여기서 전체 덮개와 농구 문구로 넘겨받는다
 * (섹션 링은 그때 숨는다 — 로딩 표시와 문구는 화면에 하나만). 문구는 6초마다 바뀐다 (store 가 고른다, lib/wait-messages).
 * 쌓임 순서(z-20): 내용 · TopBar(z-10) 위, 안내 팝업(z-30) · 시트 · 스포트라이트(z-40) · 토스트(z-50) 아래.
 * 시트가 열려 있는 동안은 흐림 덮개를 빼고 링과 문구만 — 시트 뒤 화면을 두 겹으로 어둡게 하지 않는다.
 */
import { isOverlayActive, useLoadingState } from '../store/loading'
import { WAIT_SUBLINE } from '../lib/wait-messages'
import { useModalOpen } from './use-modal'

export function LoadingHost() {
  const state = useLoadingState()
  const modalOpen = useModalOpen()
  if (!isOverlayActive(state)) return null
  const msg = state.waitMessage
  // 터치는 막지 않는다(뒤로 가기는 눌린다). 0.15초 뒤에 나타나므로 금방 끝나는 로딩에서는 번쩍이지 않는다
  return (
    <div className={`pointer-events-none fixed inset-0 z-20 flex animate-[loading-in_200ms_ease-out_150ms_both] flex-col items-center justify-center gap-3 px-6 ${modalOpen ? '' : 'bg-canvas/70 backdrop-blur-[3px]'}`}>
      <span className="size-8 animate-spin motion-reduce:animate-none rounded-full border-[3px] border-brand-line border-t-brand" aria-hidden={msg ? true : undefined} />
      {msg && (
        <div role="status" aria-live="polite" className="text-center">
          <p className="text-sm font-semibold text-ink">{msg}</p>
          <p className="mt-0.5 text-xs text-ink-2">{WAIT_SUBLINE}</p>
        </div>
      )}
    </div>
  )
}
