import { api } from './client'
import type { MyProfile, Position, SelfRankLevel, SurveyAnswerIn, SurveyMyResponse, SurveyTemplate } from './types'

export const surveyApi = {
  template: () => api<SurveyTemplate>('/surveys/onboarding', { auth: false }),
  submit: (template_id: number, answers: SurveyAnswerIn[]) =>
    api<MyProfile>('/surveys/onboarding/responses', { method: 'POST', body: { template_id, answers } }),
  /** 내가 낸 답 — 다시 할 때 채워 넣는다 */
  myResponse: () => api<SurveyMyResponse>('/surveys/onboarding/responses/me'),
  /** 설문 다시 하기 (30일에 한 번, 원하는 사람만). 아직이면 409 ALREADY_SUBMITTED */
  retake: (template_id: number, answers: SurveyAnswerIn[]) =>
    api<MyProfile>('/surveys/onboarding/responses', { method: 'PUT', body: { template_id, answers } }),
  myProfile: () => api<MyProfile>('/me/profile'),
  /** 목록 순서가 곧 선호 순서 (첫 항목 = 가장 선호) */
  updatePositions: (positions: { position: Position; can_play?: boolean; preference_rank?: number | null }[]) =>
    api<MyProfile>('/me/positions', { method: 'PUT', body: { positions } }),
  setSelfRank: (teamId: number, level: SelfRankLevel) =>
    api<MyProfile>(`/teams/${teamId}/self-rank`, { method: 'PUT', body: { level } }),
}
