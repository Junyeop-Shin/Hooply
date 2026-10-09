/**
 * 토스트 — 저장·복사·공유처럼 "됐어요" 를 짧게 알려 줄 때 (store/feedback 의 toast()).
 * 하단 고정 버튼(BottomAction · TabBar) 위에 뜨고, iOS 홈 인디케이터 영역을 피한다.
 * 스크린리더는 role="status"(aria-live polite)로, 오류는 role="alert" 로 바로 읽는다. 눌러서 바로 닫을 수 있다.
 */
import { dismissToast, useFeedback } from '../store/feedback'

export function ToastHost() {
  const toasts = useFeedback((s) => s.toasts)
  return (
    <div
      className="pointer-events-none fixed inset-x-0 z-50 mx-auto flex max-w-md flex-col items-center gap-2 px-4"
      style={{ bottom: 'calc(max(1rem, env(safe-area-inset-bottom)) + 5.5rem)' }}
      role="status" aria-live="polite"
    >
      {toasts.map((t) => (
        <button
          key={t.id} type="button" role={t.kind === 'error' ? 'alert' : undefined} onClick={() => dismissToast(t.id)}
          className={`pointer-events-auto max-w-full rounded-2xl px-4 py-3 text-left text-sm font-semibold shadow-lg ${t.kind === 'error' ? 'bg-danger-ink text-white dark:text-navy-900' : 'bg-inverse text-on-inverse'}`}
        >
          {t.text}
        </button>
      ))}
    </div>
  )
}
