/**
 * 팀 색 (유니폼) — 1 블랙 · 2 화이트 · 3 레드. 3팀 배정(참석 16명 이상)에서 세 번째 팀이 레드다.
 * 모드와 무관하게 블랙·레드는 어둡고 화이트는 밝다 (index.css 의 team-* 토큰).
 */
export type SquadTone = 'black' | 'white' | 'red'

/** 팀 기본 이름 — 백엔드 app/models/enums.DEFAULT_SQUAD_NAMES 와 같다 */
export const SQUAD_NAMES = ['블랙', '화이트', '레드'] as const
export const squadName = (no: number): string => SQUAD_NAMES[no - 1] ?? `${no}팀`

export const squadTone = (no: number): SquadTone => (no === 1 ? 'black' : no === 3 ? 'red' : 'white')

export const SQUAD_STYLE: Record<SquadTone, { card: string; sub: string; dot: string; picked: string; soft: string }> = {
  black: {
    card: 'border-team-black bg-team-black text-team-black-ink [color-scheme:dark]',
    sub: 'text-team-black-sub', dot: 'bg-team-black', picked: 'bg-court-700 text-white', soft: 'bg-white/15',
  },
  white: {
    card: 'border-line-strong bg-team-white text-team-white-ink [color-scheme:light]',
    sub: 'text-team-white-sub', dot: 'border border-line-strong bg-team-white', picked: 'bg-court-100', soft: 'bg-court-50',
  },
  red: {
    card: 'border-team-red bg-team-red text-team-red-ink [color-scheme:dark]',
    sub: 'text-team-red-sub', dot: 'bg-team-red', picked: 'bg-white/30', soft: 'bg-white/15',
  },
}

export const squadStyle = (no: number) => SQUAD_STYLE[squadTone(no)]

/** 3팀으로 나누기를 물어보는 참석 인원 — 15명이 넘으면 (16명부터) */
export const THREE_TEAM_FROM = 16

/** 2팀으로 짜도 되지만 3팀을 권하는 참석 인원 — 18명이 넘으면. 2팀도 막지 않는다(한 팀 10명 가까이 되면 대부분 벤치) */
export const THREE_TEAM_SUGGEST_FROM = 19
