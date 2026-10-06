/** 여러 화면이 같은 말로 물어야 하는 확인 문구 — 한 곳에서 관리한다 */
import type { ConfirmOptions } from '../store/feedback'

/** 참석 응답 미리 마감 — 일정 화면(S-10)과 배정 실행 화면(S-12)이 같이 쓴다 */
export const CLOSE_RSVP_CONFIRM: ConfirmOptions = {
  title: '참석 응답을 지금 마감할까요?',
  body: '인원이 확정되고 팀원은 더 이상 응답을 바꿀 수 없어요. 매니저는 대신 바꿀 수 있어요.',
  confirmLabel: '마감하기',
}
