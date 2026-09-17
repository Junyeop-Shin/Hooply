/**
 * 배정 화면의 "같은 팀으로 묶기" 그룹 계산 (S-12, FR-17).
 *
 * 묶음은 서로 겹치지 않는 그룹 목록으로 들고 있는다. 새로 묶는 사람 중 누구라도 이미 어떤 묶음에 있으면
 * 그 묶음을 버리지 않고 **하나로 합친다** — A·B 가 묶인 상태에서 "게스트 G 를 A 와 같은 팀으로" 를 승인하면
 * A·B·G 가 한 묶음이 된다. 서버도 겹치는 그룹을 Union-Find 로 합치지만, 화면에서 먼저 지워 버리면
 * 서버까지 가지 못하므로 여기서 같은 규칙을 지킨다.
 */

/** `ids` 를 묶는다. 겹치는 기존 묶음은 모두 합쳐 한 그룹이 되고, 먼저 있던 사람이 앞에 온다. */
export function mergeLock(groups: number[][], ids: number[]): number[][] {
  let merged = [...new Set(ids)]
  let rest = groups
  // 합친 그룹이 다른 그룹과 또 겹칠 수 있으므로 더 겹치는 그룹이 없을 때까지 흡수한다
  for (;;) {
    const hit = rest.filter((g) => g.some((p) => merged.includes(p)))
    if (hit.length === 0) break
    rest = rest.filter((g) => !hit.includes(g))
    merged = [...new Set([...hit.flat(), ...merged])]
  }
  return merged.length >= 2 ? [...rest, merged] : rest
}

/** 두 사람이 이미 같은 묶음에 있는지 — 승인할 필요가 없는 제안을 가리는 데 쓴다. */
export function inSameLock(groups: number[][], a: number, b: number): boolean {
  return groups.some((g) => g.includes(a) && g.includes(b))
}
