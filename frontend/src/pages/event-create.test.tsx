/**
 * S-09 일정 등록 — "지난 일정과 같게 채우기"는 입력만 채우고 저장하지 않는다(폼 제출 금지),
 * 날짜·마감은 +7일, 시작 시각을 바꾸면 종료가 +2시간 따라오되 직접 고친 뒤에는 유지된다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EventView } from '../api/types'

vi.mock('../api/events', () => ({ eventsApi: { list: vi.fn(), create: vi.fn() } }))

import { eventsApi } from '../api/events'
import { EventCreatePage } from './events'

const lastEvent = {
  id: 5, team_id: 1, title: '일요 정기전', event_date: '2026-09-06', start_time: '10:00:00', end_time: '12:00:00',
  venue: '서초 사회체육관', rsvp_deadline: '2026-09-05T13:00:00.000Z', status: 'DONE', memo: '회비 5,000원',
  attend_count: 12, my_attendance: 'ATTEND', rsvp_open: false, my_role: 'MANAGER', adopted_candidate_id: 1, run_count: 1,
  my_squad_name: null, my_assigned_position: null, quarter_count: 6, survey_open: true, my_survey_submitted: true,
  survey_responded: 8, survey_total: 12,
} as EventView

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/teams/1/events/new']}>
        <Routes><Route path="/teams/:teamId/events/new" element={<EventCreatePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement

describe('EventCreatePage', () => {
  beforeEach(() => {
    vi.mocked(eventsApi.list).mockResolvedValue({ items: [lastEvent], meta: { page: 1, size: 50, total: 1, has_next: false } })
    vi.mocked(eventsApi.create).mockResolvedValue({ ...lastEvent, id: 9 })
  })

  it('채우기는 값만 넣고 일정을 만들지 않는다 (날짜·마감은 일주일 뒤)', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '채우기' }))
    expect(eventsApi.create).not.toHaveBeenCalled()  // 폼이 제출되면 안 된다
    expect(input('제목 (선택)')).toHaveValue('일요 정기전')
    expect(input('날짜')).toHaveValue('2026-09-13')      // 9/6 + 7일
    expect(input('시작')).toHaveValue('10:00')
    expect(input('종료')).toHaveValue('12:00')
    expect(input('장소')).toHaveValue('서초 사회체육관')
    expect(input('응답 마감 (선택)')).toHaveValue('2026-09-12')  // 마감도 +7일
    expect(input('메모 (선택)')).toHaveValue('회비 5,000원')
    // 채운 뒤 사용자가 고칠 수 있고, 제출 버튼을 눌러야 등록된다
    await user.clear(input('제목 (선택)'))
    await user.type(input('제목 (선택)'), '번개 모임')
    await user.click(screen.getByRole('button', { name: '등록하고 응답 받기' }))
    expect(eventsApi.create).toHaveBeenCalledWith(1, expect.objectContaining({ title: '번개 모임', event_date: '2026-09-13' }))
  })

  it('시작 시각을 바꾸면 종료가 2시간 뒤로 따라오고, 종료를 직접 고치면 그대로 둔다', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '채우기' })
    await user.clear(input('시작'))
    await user.type(input('시작'), '19:30')
    expect(input('종료')).toHaveValue('21:30')
    // 직접 3시간짜리로 바꾸면, 이후 시작을 바꿔도 종료는 유지된다
    await user.clear(input('종료'))
    await user.type(input('종료'), '22:30')
    await user.clear(input('시작'))
    await user.type(input('시작'), '20:00')
    expect(input('종료')).toHaveValue('22:30')
  })

  it('마감 날짜를 고르면 마감 시각이 밤 10시로 채워진다', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByRole('button', { name: '채우기' })
    expect(input('마감 시각')).toBeDisabled()
    await user.type(input('응답 마감 (선택)'), '2026-09-19')
    expect(input('마감 시각')).toHaveValue('22:00')
    expect(input('마감 시각')).toBeEnabled()
  })
})
