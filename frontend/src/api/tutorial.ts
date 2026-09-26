import { api } from './client'
import type { TutorialUpdate, TutorialView } from './types'

/** 시작 안내 — 홈 체크리스트(단계 판정은 서버)와 기능별 첫 안내 */
export const tutorialApi = {
  get: () => api<TutorialView>('/me/tutorial'),
  update: (body: TutorialUpdate) => api<TutorialView>('/me/tutorial', { method: 'PUT', body }),
}
