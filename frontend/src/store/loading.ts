/**
 * 지금 화면에 걸려 있는 <Spinner /> 수 — 두 층으로 센다.
 *   page    : <Spinner page />  화면 전체가 비어 있는 로딩. LoadingHost(components/loading)가 화면을 덮고 가운데에 하나 그린다
 *   section : <Spinner />       화면 일부(섹션)만 불러오는 중. 그 자리에 작은 링을 그리고 화면은 가리지 않는다
 * 어느 층이든 SLOW_AFTER_MS(5초)를 넘게 이어지면 서버가 깨는 중일 수 있으니 기다림 문구(`waitMessage`)가 켜지고 ROTATE_MS 마다
 * 바뀐다. 그때는 LoadingHost 가 전체 덮개와 문구로 넘겨받고 섹션 링은 숨는다 — 로딩 표시와 문구가 화면에 하나만 남게.
 */
import { useLayoutEffect, useSyncExternalStore } from 'react'
import { pickWaitMessage, ROTATE_MS, SLOW_AFTER_MS } from '../lib/wait-messages'

export type LoadingTier = 'page' | 'section'
export interface LoadingSnapshot {
  page: number
  section: number
  /** 로딩이 5초를 넘게 이어지는 중이면 기다림 문구, 아니면 null */
  waitMessage: string | null
}

let snapshot: LoadingSnapshot = { page: 0, section: 0, waitMessage: null }
let slowTimer: number | undefined
let rotateTimer: number | undefined
const listeners = new Set<() => void>()
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
const set = (next: Partial<LoadingSnapshot>) => { snapshot = { ...snapshot, ...next }; listeners.forEach((fn) => fn()) }

const stopTimers = () => {
  if (slowTimer !== undefined) { window.clearTimeout(slowTimer); slowTimer = undefined }
  if (rotateTimer !== undefined) { window.clearInterval(rotateTimer); rotateTimer = undefined }
}

const change = (tier: LoadingTier, by: number) => {
  const wasActive = snapshot.page + snapshot.section > 0
  const n = Math.max(0, snapshot[tier] + by)
  set(tier === 'page' ? { page: n } : { section: n })
  const active = snapshot.page + snapshot.section > 0
  if (active && !wasActive) {
    // 로딩이 시작됐다 — 5초 뒤에도 이어지면 느린 것으로 보고 문구를 띄우고 6초마다 바꾼다
    slowTimer = window.setTimeout(() => {
      slowTimer = undefined
      set({ waitMessage: pickWaitMessage() })
      rotateTimer = window.setInterval(() => set({ waitMessage: pickWaitMessage(snapshot.waitMessage) }), ROTATE_MS)
    }, SLOW_AFTER_MS)
  } else if (!active && wasActive) {
    stopTimers()
    if (snapshot.waitMessage !== null) set({ waitMessage: null })
  }
}

/** <Spinner /> 가 걸려 있는 동안 그 층의 로딩 중으로 센다 */
export function useLoadingMark(tier: LoadingTier) {
  useLayoutEffect(() => { change(tier, 1); return () => change(tier, -1) }, [tier])
}

export const useLoadingState = () => useSyncExternalStore(subscribe, () => snapshot)

/** 전체 덮개(LoadingHost)가 떠 있어야 하는가 — 화면 전체 로딩이거나, 어느 로딩이든 5초를 넘겼을 때 */
export const isOverlayActive = (s: LoadingSnapshot) => s.page > 0 || s.waitMessage !== null
export const useOverlayActive = () => useSyncExternalStore(subscribe, () => isOverlayActive(snapshot))

/** 시험용 — 상태를 처음으로 */
export function resetLoadingForTest() {
  stopTimers()
  set({ page: 0, section: 0, waitMessage: null })
}
