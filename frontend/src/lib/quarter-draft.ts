/** 쿼터 기록 화면(S-15)의 초안 판단 — 화면 밖에서 시험할 수 있게 뺐다 */

/** 득점 상한 — 백엔드 app/schemas/game.py 와 같은 값 (한 쿼터 한 팀) */
export const MAX_SCORE = 99

type Lineup = { black: number[]; white: number[]; home: number; away: number }

/** 두 칸의 팀과 출전 명단을 한 줄로 (순서 무관) */
export const lineupSig = (q: Lineup) =>
  `${q.home}:${[...q.black].sort((a, b) => a - b).join(',')}|${q.away}:${[...q.white].sort((a, b) => a - b).join(',')}`

/**
 * 점수가 0:0 이고 만든 뒤 명단을 건드리지 않은 쿼터 — 지워도 잃는 것이 없어 묻지 않는다.
 * seed(만들 때의 명단)가 없는 쿼터는 서버에서 받은 기록이라 늘 묻는다.
 */
export const isPristineQuarter = (q: Lineup & { black_score: number; white_score: number; seed?: string }) =>
  q.black_score === 0 && q.white_score === 0 && q.seed !== undefined && q.seed === lineupSig(q)

type QuarterDraft = Lineup & { quarter_no: number; black_score: number; white_score: number; duration_min: number; seed?: string }

/** 쿼터 하나를 비교용 한 줄로 — 명단 순서와 seed(화면에서 만든 표시)는 무시한다 */
const quarterSig = (q: QuarterDraft) => `${q.quarter_no}|${q.black_score}:${q.white_score}|${q.duration_min}|${lineupSig(q)}`

/**
 * 화면의 초안이 서버 기록(fromServer)을 그대로 옮겨 온 것과 같은가 — 매니저가 아직 아무것도 고치지 않았다는 뜻.
 * 서버 기록이 없을 때는 빈 쿼터 1개를 미리 만들어 주므로, 그 쿼터가 만든 그대로(0:0 · 명단 그대로)면 역시 "안 고쳤다".
 * 다른 기기에서 기록이 바뀌어 서버 기록이 달라졌을 때, 이 값이 참이면 조용히 새 기록으로 바꿔 끼우고 거짓이면 매니저에게 알린다.
 */
export function draftMatchesServer(draft: QuarterDraft[], fromServer: QuarterDraft[]): boolean {
  if (fromServer.length === 0) return draft.every(isPristineQuarter)
  return draft.length === fromServer.length && draft.every((q, i) => quarterSig(q) === quarterSig(fromServer[i]))
}
