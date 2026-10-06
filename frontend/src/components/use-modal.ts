import { useEffect, useRef, useSyncExternalStore, type RefObject } from 'react'

/* ---------- 모달 공통: 포커스 가두기 · 뒤 화면 스크롤 잠금 · Esc ---------- */

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
/** 열린 모달 순서 — 시트 위에 확인 시트가 겹치면 키 입력은 맨 위 것만 받는다 */
const modalStack: number[] = []
let modalSeq = 0
let savedOverflow = ''
// 모달이 열려 있는지를 밖(LoadingHost)에서도 읽을 수 있게 — 열고 닫을 때마다 알린다
const openListeners = new Set<() => void>()
const subscribeOpen = (fn: () => void) => { openListeners.add(fn); return () => { openListeners.delete(fn) } }
const notifyOpen = () => openListeners.forEach((fn) => fn())

/** 시트 · 확인 시트 · 안내 팝업 중 하나라도 열려 있는가 */
export const useModalOpen = () => useSyncExternalStore(subscribeOpen, () => modalStack.length > 0)

/**
 * 모달이 열려 있는 동안: 포커스를 안으로 옮기고(Tab 이 밖으로 나가지 않게), 뒤 화면 스크롤을 막고,
 * Esc 로 닫고(onClose 가 있을 때), 닫히면 열기 전에 누르던 버튼으로 포커스를 돌려준다.
 */
export function useModal(ref: RefObject<HTMLElement | null>, onClose?: () => void) {
  const closeRef = useRef(onClose)
  useEffect(() => { closeRef.current = onClose })
  useEffect(() => {
    const id = ++modalSeq
    const el = ref.current
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    modalStack.push(id)
    notifyOpen()
    if (modalStack.length === 1) { savedOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden' }
    // autoFocus 로 이미 안쪽 칸에 포커스가 들어왔으면 그대로 두고, 아니면 시트 자체에
    if (el && !el.contains(document.activeElement)) el.focus({ preventScroll: true })
    const onKey = (e: KeyboardEvent) => {
      if (modalStack[modalStack.length - 1] !== id || !el) return
      if (e.key === 'Escape' && closeRef.current) { e.preventDefault(); closeRef.current(); return }
      if (e.key !== 'Tab') return
      const items = Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) { e.preventDefault(); el.focus(); return }
      const first = items[0], last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === el || !el.contains(active))) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (active === last || !el.contains(active))) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      const at = modalStack.indexOf(id)
      if (at >= 0) modalStack.splice(at, 1)
      notifyOpen()
      if (modalStack.length === 0) document.body.style.overflow = savedOverflow
      if (opener && opener.isConnected) opener.focus({ preventScroll: true })
    }
  }, [ref])
}

