/**
 * S-12 확정하지 않은 배정안 (docs/09 2-4) — 이어 보기 링크, 직접 옮긴 안을 지우기 전 확인.
 * API 는 vi.mock 으로 대체한다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AssignmentRunView, AttendanceView, CandidateView, EventView, PlayerCard } from '../api/types'

vi.mock('../api/events', () => ({ eventsApi: { get: vi.fn(), attendances: vi.fn(), suggestions: vi.fn(), closeRsvp: vi.fn() } }))
vi.mock('../api/assignments', () => ({ assignmentsApi: { runs: vi.fn(), validate: vi.fn(), run: vi.fn(), lastConstraints: vi.fn() } }))

import { assignmentsApi } from '../api/assignments'
import { eventsApi } from '../api/events'
import { answerConfirm, useFeedback } from '../store/feedback'
import { AssignPage } from './assignment'

const player = (id: number): PlayerCard => ({
  id, user_id: id, kind: 'MEMBER', display_name: `선수${id}`, role: 'PLAYER', profile_image_url: null, height_cm: null,
  skill_grade: 'C', primary_position: 'SF', playable_positions: ['SF'], attendance_rate: null, skill_confidence: null,
})
const attend = (id: number): AttendanceView => ({
  player: player(id), status: 'ATTEND', note: null, responded_at: null, registered_by: null, registered_by_name: null,
  team_lock_request_player_id: null, team_lock_request_player_name: null, can_edit: true,
})
const event = { id: 1, team_id: 1, title: '일요 정기전', event_date: '2026-11-22', start_time: '10:00:00', end_time: '12:00:00', status: 'CLOSED', rsvp_open: false, my_role: 'MANAGER', adopted_candidate_id: null, quarter_count: 0 } as EventView
const candidate = (edited: boolean): CandidateView => ({
  id: 7, strategy: 'SKILL', total_score: null, metrics: {}, explanation: null, is_adopted: false,
  squads: [{ squad_no: 1, squad_name: '블랙', avg_skill: null, members: [], assigned_positions: {}, manual_override_ids: edited ? [3] : [], avg_height_cm: null }],
} as unknown as CandidateView)
const runOf = (edited: boolean): AssignmentRunView => ({ id: 42, event_id: 1, team_count: 2, created_at: '2026-11-20T10:00:00Z', constraints: { lock_groups: [], separate_groups: [], pins: [] }, candidates: [candidate(edited)], warnings: [] })

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/events/1/assign']}>
        <Routes>
          <Route path="/events/:eventId/assign" element={<AssignPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AssignPage — 확정하지 않은 배정안', () => {
  beforeEach(() => {
    sessionStorage.clear()
    useFeedback.setState({ pending: null, toasts: [] })
    vi.mocked(eventsApi.get).mockResolvedValue(event)
    vi.mocked(eventsApi.attendances).mockResolvedValue({ items: Array.from({ length: 10 }, (_, i) => attend(i + 1)) } as never)
    vi.mocked(eventsApi.suggestions).mockResolvedValue({ items: [] } as never)
    vi.mocked(assignmentsApi.validate).mockResolvedValue({ feasible: true, violations: [], warnings: [] })
    vi.mocked(assignmentsApi.run).mockResolvedValue(runOf(false))
  })

  it('이어 보기로 그 배정안 결과 화면에 간다', async () => {
    vi.mocked(assignmentsApi.runs).mockResolvedValue({ items: [runOf(false)] })
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '이어 보기' }))
    expect(await screen.findByTestId('where')).toHaveTextContent('/assignments/runs/42')
  })

  it('직접 옮긴 안이 있으면 새로 나누기 전에 묻고, 취소하면 실행하지 않는다', async () => {
    vi.mocked(assignmentsApi.runs).mockResolvedValue({ items: [runOf(true)] })
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByText(/직접 옮긴 자리까지 그대로 있어요/)).toBeInTheDocument()
    const btn = screen.getByRole('button', { name: '3가지 배정안 만들기' })
    await waitFor(() => expect(btn).toBeEnabled())
    await user.click(btn)
    await waitFor(() => expect(useFeedback.getState().pending?.title).toBe('직접 옮긴 배정안이 지워져요'))
    answerConfirm(false)
    await waitFor(() => expect(useFeedback.getState().pending).toBeNull())
    expect(assignmentsApi.run).not.toHaveBeenCalled()
  })

  it('옮긴 것이 없으면 묻지 않고 바로 나눈다', async () => {
    vi.mocked(assignmentsApi.runs).mockResolvedValue({ items: [runOf(false)] })
    const user = userEvent.setup()
    renderPage()
    const btn = await screen.findByRole('button', { name: '3가지 배정안 만들기' })
    await waitFor(() => expect(btn).toBeEnabled())
    await user.click(btn)
    await waitFor(() => expect(assignmentsApi.run).toHaveBeenCalled())
    expect(useFeedback.getState().pending).toBeNull()
  })
})
