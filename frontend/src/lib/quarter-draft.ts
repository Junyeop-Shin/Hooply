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
