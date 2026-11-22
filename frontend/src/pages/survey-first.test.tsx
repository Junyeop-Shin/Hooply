/**
 * 처음 하는 설문을 마친 뒤 (docs/10 F-3) — 팀에 먼저 가입하고 설문을 나중에 하는 사람이 생겼으므로,
 * 설문을 마치면 "이 팀에서 내 위치"를 아직 안 정한 팀의 그 문항으로 보낸다(팀을 나누는 데 가장 쓸모 있는 답이다).
 * 그런 팀이 없으면 전처럼 맡겨 둔 주소나 홈으로.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MyProfile, SurveyTemplate, UserDetail } from '../api/types'

vi.mock('../api/auth', () => ({ authApi: { me: vi.fn() }, ME_STALE: 0 }))
vi.mock('../api/survey', () => ({ surveyApi: { template: vi.fn(), myResponse: vi.fn(), retake: vi.fn(), submit: vi.fn(), myProfile: vi.fn() } }))

import { authApi } from '../api/auth'
import { surveyApi } from '../api/survey'
import { SurveyPage } from './survey'

const q = (id: number, code: string, text: string, answer_type: 'ANCHOR_4' | 'MULTI_CHIP', section = 'A') => ({
  id, section, code, question_text: text, answer_type, display_order: id, help_text: null, group_label: null,
  options: [1, 2, 3].map((n) => ({ id: id * 10 + n, code: `${code}_${n}`, option_order: n, label: `${text} 답${n}` })),
})
const template: SurveyTemplate = { template_id: 2, version: 2, name: '온보딩', questions: [q(1, 'A2', '구력', 'ANCHOR_4'), q(2, 'B1', '공격 옵션', 'MULTI_CHIP', 'B')] }
const profile = (teams: { team_id: number; self_rank_level: string | null }[]) => ({ teams: teams.map((t) => ({ team_name: `팀${t.team_id}`, ...t })) } as unknown as MyProfile)

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{loc.pathname}{(loc.state as { after?: string } | null)?.after ? ` after=${(loc.state as { after: string }).after}` : ''}</p>
}

async function finishSurvey() {
  const user = userEvent.setup()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/survey']}>
        <Routes>
          <Route path="/survey" element={<SurveyPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await user.click(await screen.findByRole('button', { name: /구력 답2/ }))  // 단일 선택은 고르면 다음 문항으로 넘어간다
  await user.click(await screen.findByRole('button', { name: '공격 옵션 답1' }))
  await user.click(screen.getByRole('button', { name: '설문 마치기' }))
  await waitFor(() => expect(surveyApi.submit).toHaveBeenCalledTimes(1))
  return screen.findByTestId('where')
}

describe('SurveyPage — 처음 하는 설문을 마친 뒤', () => {
  beforeEach(() => {
    sessionStorage.clear(); localStorage.clear()
    vi.mocked(authApi.me).mockResolvedValue({ id: 1, name: '민수', onboarding_completed: false } as UserDetail)
    vi.mocked(surveyApi.template).mockResolvedValue(template)
    vi.mocked(surveyApi.submit).mockReset().mockResolvedValue({} as MyProfile)
  })

  it('내 위치를 아직 안 정한 팀이 있으면 그 팀의 내 위치 문항으로 간다', async () => {
    vi.mocked(surveyApi.myProfile).mockResolvedValue(profile([{ team_id: 5, self_rank_level: 'MID' }, { team_id: 3, self_rank_level: null }]))
    const where = await finishSurvey()
    expect(where).toHaveTextContent('/teams/3/self-rank')
    expect(where).toHaveTextContent('after=survey')  // 그 화면이 "팀 가입 완료" 대신 "설문 완료" 로 맞이한다
  })

  it('팀이 없거나 모두 정했으면 홈으로 간다', async () => {
    vi.mocked(surveyApi.myProfile).mockResolvedValue(profile([{ team_id: 5, self_rank_level: 'MID' }]))
    expect(await finishSurvey()).toHaveTextContent(/^\/$/)
  })

  it('내 팀을 못 받아도 설문은 저장됐으니 홈으로 간다', async () => {
    vi.mocked(surveyApi.myProfile).mockRejectedValue(new Error('offline'))
    expect(await finishSurvey()).toHaveTextContent(/^\/$/)
  })
})
