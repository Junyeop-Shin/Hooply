/**
 * 설문 다시 하기 (docs/09 3-10) — 강제 없이 프로필의 링크로만 들어온다.
 * 지난 답이 채워진 채 시작하고, 달라진 것만 고쳐 PUT 으로 저장한다. 아직 30일이 안 됐으면 날짜만 알려 준다.
 * API 는 vi.mock 으로 대체한다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MyProfile, SurveyMyResponse, SurveyTemplate, UserDetail } from '../api/types'

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
const previous = (retakeAt: string): SurveyMyResponse => ({
  template_id: 2, submitted_at: '2026-09-01T00:00:00Z', retake_at: retakeAt,
  answers: [{ question_id: 1, selected_option_ids: [12], numeric_value: null }, { question_id: 2, selected_option_ids: [21, 23], numeric_value: null }],
})

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderPage(path = '/survey?retake=1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/survey" element={<SurveyPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SurveyPage — 다시 하기', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.mocked(authApi.me).mockResolvedValue({ id: 1, name: '허재', onboarding_completed: true } as UserDetail)
    vi.mocked(surveyApi.template).mockResolvedValue(template)
    vi.mocked(surveyApi.retake).mockResolvedValue({} as MyProfile)
  })

  it('지난 답이 채워져 있고, 달라진 것만 고쳐 PUT 으로 저장한 뒤 프로필로 간다', async () => {
    vi.mocked(surveyApi.myResponse).mockResolvedValue(previous('2026-10-01T00:00:00Z'))
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByText(/지난번 답이 채워져 있어요/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /구력 답2/ })).toHaveAttribute('aria-pressed', 'true')
    // 그대로 두고 다음으로 — 지난 답이 있어 바로 넘어갈 수 있다
    await user.click(screen.getByRole('button', { name: '다음' }))
    expect(screen.getByRole('button', { name: '공격 옵션 답1' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: '공격 옵션 답2' }))  // 하나 더 고른다
    await user.click(screen.getByRole('button', { name: '설문 마치기' }))
    await waitFor(() => expect(surveyApi.retake).toHaveBeenCalledWith(2, [
      { question_id: 1, selected_option_ids: [12] },
      { question_id: 2, selected_option_ids: [21, 23, 22] },
    ]))
    expect(surveyApi.submit).not.toHaveBeenCalled()
    expect(await screen.findByTestId('where')).toHaveTextContent('/me')
  })

  it('아직 30일이 안 됐으면 설문 대신 다시 할 수 있는 날짜를 알려 준다', async () => {
    const at = new Date(Date.now() + 10 * 86_400_000)
    vi.mocked(surveyApi.myResponse).mockResolvedValue(previous(at.toISOString()))
    renderPage()
    expect(await screen.findByText('아직 다시 할 수 없어요')).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`${at.getMonth() + 1}월 ${at.getDate()}일부터`))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '설문 마치기' })).not.toBeInTheDocument()
  })

  it('설문 버전이 바뀌었으면 지난 답을 채우지 않는다', async () => {
    vi.mocked(surveyApi.myResponse).mockResolvedValue({ ...previous('2026-10-01T00:00:00Z'), template_id: 1 })
    renderPage()
    expect(await screen.findByRole('button', { name: /구력 답2/ })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '다음' })).toBeDisabled()
  })

  it('이미 설문을 한 사람이 그냥 /survey 로 오면 전처럼 홈으로 보낸다 (다시 하라고 하지 않는다)', async () => {
    renderPage('/survey')
    expect(await screen.findByTestId('where')).toHaveTextContent('/')
    expect(surveyApi.myResponse).not.toHaveBeenCalled()
  })
})
