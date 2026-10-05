/**
 * 지금 화면에 걸려 있는 <Spinner /> 수. 하나라도 있으면 LoadingHost(components/loading)가 화면 가운데에 로딩 표시를 하나 그린다.
 */
import { useLayoutEffect, useSyncExternalStore } from 'react'

let pending = 0  // 지금 화면에 걸려 있는 <Spinner /> 수
const listeners = new Set<() => void>()
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
const change = (by: number) => { pending += by; listeners.forEach((fn) => fn()) }

/** <Spinner /> 가 걸려 있는 동안 로딩 중으로 센다 */
export function useLoadingMark() {
  useLayoutEffect(() => { change(1); return () => change(-1) }, [])
}

export const useIsLoading = () => useSyncExternalStore(subscribe, () => pending > 0)
