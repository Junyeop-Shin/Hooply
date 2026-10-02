/**
 * 화면 피드백 (토스트 · 확인 시트). 브라우저 기본 alert()/confirm() 대신 쓴다 —
 * 기본 창은 카카오톡 인앱 브라우저에서 모양이 제각각이고, 화면 흐름을 멈추며, 접근성 이름도 없다.
 *
 * - toast(text)        : 아래쪽에 잠깐 뜨는 한 줄 알림 (components/toast.tsx 의 ToastHost 가 그린다)
 * - confirm({...})     : 아래에서 올라오는 확인 시트. 누른 버튼에 따라 true/false 로 끝나는 Promise
 *                        (components/confirm-sheet.tsx 의 ConfirmHost 가 그린다)
 * 둘 다 컴포넌트 밖(mutation 콜백, queryClient)에서도 부를 수 있게 zustand 스토어로 둔다.
 */
import { create } from 'zustand'

export type ToastKind = 'info' | 'error'
export interface ToastItem { id: number; text: string; kind: ToastKind }

export interface ConfirmOptions {
  title: string
  body?: string
  /** 확인 버튼 문구 (기본 "확인") */
  confirmLabel?: string
  /** 취소 버튼 문구 (기본 "취소") */
  cancelLabel?: string
  /** 지우기처럼 되돌릴 수 없는 일이면 붉은 버튼 */
  danger?: boolean
}
interface PendingConfirm extends ConfirmOptions { id: number; resolve: (ok: boolean) => void }

interface FeedbackState {
  toasts: ToastItem[]
  pending: PendingConfirm | null
}

export const useFeedback = create<FeedbackState>()(() => ({ toasts: [], pending: null }))

/** 토스트가 떠 있는 시간 — 오류는 읽을 시간이 조금 더 필요하다 */
export const TOAST_MS = { info: 2500, error: 4000 } as const
let seq = 0

/** 한 줄 알림. 같은 문구가 이미 떠 있으면 하나만 남긴다 (같은 오류를 두 번 보여 주지 않게) */
export function toast(text: string, kind: ToastKind = 'info') {
  const { toasts } = useFeedback.getState()
  if (toasts.some((t) => t.text === text)) return
  const id = ++seq
  useFeedback.setState({ toasts: [...toasts.slice(-2), { id, text, kind }] })  // 많아야 3개
  setTimeout(() => dismissToast(id), TOAST_MS[kind])
}

export function dismissToast(id: number) {
  useFeedback.setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
}

/** 확인 시트를 띄우고 사용자의 답(true = 확인)을 기다린다. 다른 확인이 떠 있으면 그건 취소로 끝낸다 */
export function confirm(opts: ConfirmOptions): Promise<boolean> {
  const prev = useFeedback.getState().pending
  if (prev) prev.resolve(false)
  return new Promise<boolean>((resolve) => {
    const id = ++seq
    useFeedback.setState({
      pending: {
        ...opts, id,
        resolve: (ok) => {
          if (useFeedback.getState().pending?.id === id) useFeedback.setState({ pending: null })
          resolve(ok)
        },
      },
    })
  })
}

/** 떠 있는 확인 시트를 답한다 (ConfirmHost · 화면 이동 시) */
export function answerConfirm(ok: boolean) {
  useFeedback.getState().pending?.resolve(ok)
}
