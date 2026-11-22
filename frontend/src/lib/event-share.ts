/**
 * 일정 알리기 문구 (docs/10 F-1, FR-66) — 매니저가 응답을 받는 일정을 카카오톡 단톡방에 보낸다.
 * 화면이 이미 받은 값으로 만든다: 누르는 순간 공유 창이 떠야 하는데, 서버를 한 번 더 부르면 그 사이 브라우저가 창을 막을 수 있다.
 */
import type { EventView } from '../api/types'
import { fmtDeadline, fmtEvent } from './format'

/** 카카오톡 텍스트 메시지의 본문 상한 */
export const SHARE_TEXT_MAX = 200
/** 아직 응답 안 한 팀원의 이름은 이 인원까지만 적는다. 그보다 많으면 사람 수만 */
export const SHARE_NAMES_MAX = 10
const NAMES_LABEL = '아직 응답 안 한 분:'

export interface EventShareInput {
  /** 참석 인원 (게스트 포함) */
  attend: number
  /** 응답한 팀원 수 (참석 + 불참). 0 이면 아직 아무도 응답하지 않은 것 */
  responded: number
  /** 아직 응답 안 한 팀원 이름 */
  pending: string[]
}

/**
 * "[HOOPLY] 제목 · 11/29 (일) 10:00~12:00 / 장소 / 참석 9명 · 미응답 3명 / 아직 응답 안 한 분: … / (마감)까지 참석 여부를 알려 주세요."
 * - 아직 아무도 응답하지 않았으면 인원 · 이름 줄을 뺀다 (전원을 미응답으로 적어 봐야 소음이다)
 * - 이름은 전부 적거나 아예 안 적는다 — 일부만 적으면 그 사람들만 지목하게 된다. 10명을 넘거나 200자를 넘기면 사람 수만
 * - 모두 응답했으면 응답 요청 문구를 뺀다
 */
export function eventShareText(e: EventView, a: EventShareInput): string {
  const head = [`[HOOPLY] ${e.title ? `${e.title} · ` : ''}${fmtEvent(e)}`]
  if (e.venue) head.push(e.venue)
  const anyone = a.attend > 0 || a.responded > 0
  if (anyone) head.push(a.pending.length ? `참석 ${a.attend}명 · 미응답 ${a.pending.length}명` : `참석 ${a.attend}명 · 모두 응답했어요`)
  const ask = anyone && !a.pending.length ? [] : [`${e.rsvp_deadline ? `${fmtDeadline(e.rsvp_deadline)}까지 ` : ''}참석 여부를 알려 주세요.`]
  const named = a.responded > 0 && a.pending.length > 0 && a.pending.length <= SHARE_NAMES_MAX
  if (named) {
    const withNames = [...head, `${NAMES_LABEL} ${a.pending.join(', ')}`, ...ask].join('\n')
    if (withNames.length <= SHARE_TEXT_MAX) return withNames
  }
  const plain = [...head, ...ask].join('\n')
  return plain.length <= SHARE_TEXT_MAX ? plain : `${plain.slice(0, SHARE_TEXT_MAX - 1)}…`
}

/** 문구에 미응답 이름이 실렸는지 — 화면이 "이름도 함께 보내요" 를 미리 알릴 때 쓴다 */
export const sharesNames = (text: string) => text.includes(NAMES_LABEL)

/** 받은 사람이 눌러 들어올 일정 주소 (로그인이 풀려 있으면 로그인 뒤 이 주소로 돌아온다) */
export const eventShareUrl = (eventId: number) => `${window.location.origin}/events/${eventId}`
