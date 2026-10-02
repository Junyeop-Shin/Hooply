/**
 * 실력 정렬(S-19) 순서 바꾸기. 휴대폰에서는 끌어 놓기(HTML5 DnD)가 되지 않으므로
 * "카드를 눌러 집고 → 놓을 자리의 카드를 누르기" 를 쓴다. 같은 카드를 다시 누르면 내려놓는다(취소).
 */

/** from 자리의 항목을 빼서 to 자리에 넣는다. 범위를 벗어나면 그대로 */
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  if (from < 0 || from >= list.length || to < 0 || to >= list.length || from === to) return [...list]
  const next = [...list]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

export interface TapState<T> { order: T[]; picked: number | null }

/** i 번째 카드를 눌렀을 때 — 아무것도 안 집었으면 집고, 같은 카드면 내려놓고, 다른 카드면 그 자리로 옮긴다 */
export function tapReorder<T>(state: TapState<T>, i: number): TapState<T> {
  if (state.picked === null) return { order: state.order, picked: i }
  if (state.picked === i) return { order: state.order, picked: null }
  return { order: moveItem(state.order, state.picked, i), picked: null }
}
