/**
 * 확인 시트 — 브라우저 기본 confirm() 대신 (store/feedback 의 confirm()). 공용 Sheet 위에 만든다.
 * 화면을 옮기면 떠 있던 확인은 취소로 끝낸다 (다른 화면에서 엉뚱한 일을 확정하지 않게).
 */
import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { answerConfirm, useFeedback } from '../store/feedback'
import { Button, Sheet } from './ui'

export function ConfirmHost() {
  const pending = useFeedback((s) => s.pending)
  const { pathname } = useLocation()
  useEffect(() => () => answerConfirm(false), [pathname])
  if (!pending) return null
  return (
    <Sheet key={pending.id} label={pending.title} title={pending.title} onClose={() => answerConfirm(false)} tall={false}>
      {pending.body && <p className="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-2">{pending.body}</p>}
      <div className="mt-5 flex gap-2">
        <Button variant="ghost" className="shrink-0 px-5" onClick={() => answerConfirm(false)}>{pending.cancelLabel ?? '취소'}</Button>
        <Button full variant={pending.danger ? 'danger' : 'primary'} onClick={() => answerConfirm(true)}>{pending.confirmLabel ?? '확인'}</Button>
      </div>
    </Sheet>
  )
}
