/**
 * S-16 경기 후 투표 — 우리 팀/상대 팀 각 2명 제한, 이유까지 고르면 자동 접힘, 종료 전 안내.
 * API 는 vi.mock 으로 대체한다 (네트워크 없음).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { EventView, PlayerCard, VoteTargets } from '../api/types'

vi.mock('../api/events', () => ({ eventsApi: { get: vi.fn() } }))
vi.mock('../api/peer', () => ({ peerApi: { targets: vi.fn(), submit: vi.fn() } }))

import { eventsApi } from '../api/events'
import { peerApi } from '../api/peer'
import { answerConfirm, useFeedback } from '../store/feedback'
import { VotePage } from './vote'

const player = (id: number, name: string): PlayerCard => ({
  id, user_id: id, kind: 'MEMBER', display_name: name, role: 'PLAYER', profile_image_url: null, height_cm: null,
  skill_grade: null, primary_position: 'SF', playable_positions: ['SF'], attendance_rate: null, skill_confidence: null,
})
const event = { id: 1, team_id: 1, title: '일요 정기전', event_date: '2026-09-06', start_time: '10:00:00', end_time: '12:00:00', venue: null, rsvp_deadline: null, status: 'DONE', memo: null, attend_count: 6, my_attendance: 'ATTEND', rsvp_open: false, my_role: 'PLAYER', adopted_candidate_id: 1, run_count: 1, my_squad_name: '블랙', my_assigned_position: null, quarter_count: 0, survey_open: true, my_survey_submitted: false, survey_responded: 0, survey_total: 6 } as EventView
const targets: VoteTargets = {
  open: true, opens_at: '2026-09-06T12:00:00+09:00', already_submitted: false, my_votes: [],
  candidates: [
    { player: player(2, '서장훈'), squad_no: 1, squad_name: '블랙', is_same_team: true },
    { player: player(3, '이상민'), squad_no: 1, squad_name: '블랙', is_same_team: true },
    { player: player(4, '현주엽'), squad_no: 1, squad_name: '블랙', is_same_team: true },
    { player: player(5, '문경은'), squad_no: 2, squad_name: '화이트', is_same_team: false },
    { player: player(6, '김주성'), squad_no: 2, squad_name: '화이트', is_same_team: false },
  ],
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/events/1/vote']}>
        <Routes><Route path="/events/:eventId/vote" element={<VotePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('VotePage', () => {
  beforeEach(() => {
    vi.mocked(eventsApi.get).mockResolvedValue(event)
    vi.mocked(peerApi.targets).mockResolvedValue(targets)
    vi.mocked(peerApi.submit).mockResolvedValue({ ...targets, already_submitted: true })
  })

  it('우리 팀은 2명까지만 고를 수 있고, 이유까지 고르면 목록이 접힌다', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByText('우리 팀에서')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /서장훈/ }))
    await user.click(screen.getByRole('button', { name: /이상민/ }))
    // 3번째는 비활성
    expect(screen.getByRole('button', { name: /현주엽/ })).toBeDisabled()
    expect(screen.getByText('2/2명 골랐어요')).toBeInTheDocument()
    // 아직 이유를 안 골랐으니 목록은 그대로
    expect(screen.getByRole('button', { name: /현주엽/ })).toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: '패스가 좋았어요' })[0])
    await user.click(screen.getAllByRole('button', { name: '템포가 잘 맞았어요' })[1])  // 두 번째 선택자(이상민)의 칩
    // 이유까지 고르면 접히고 고치기 버튼과 이름 칩만 남는다
    expect(await screen.findByRole('button', { name: '고치기' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /현주엽/ })).not.toBeInTheDocument()
    // 상대 팀 이유 칩은 상대 맥락 문구
    await user.click(screen.getByRole('button', { name: /문경은/ }))
    expect(screen.getByRole('button', { name: '패스가 인상적이었어요' })).toBeInTheDocument()
    // 한 번 내면 못 고치므로 고른 사람을 확인받은 뒤에 낸다
    await user.click(screen.getByRole('button', { name: '3명 뽑고 투표 마치기' }))
    expect(peerApi.submit).not.toHaveBeenCalled()
    expect(useFeedback.getState().pending?.body).toContain('서장훈, 이상민, 문경은')
    answerConfirm(true)
    await waitFor(() => expect(peerApi.submit).toHaveBeenCalled())
    expect(peerApi.submit).toHaveBeenCalledWith(1, expect.arrayContaining([
      expect.objectContaining({ target_player_id: 2, vote_type: 'PLAY_AGAIN', reason_tag: 'PASS' }),
      expect.objectContaining({ target_player_id: 5, vote_type: 'PLAY_AGAIN' }),
    ]))
  })

  it('종료 전이면 폼 대신 안내만 보여준다', async () => {
    vi.mocked(peerApi.targets).mockRejectedValue(new ApiError(403, { code: 'SURVEY_NOT_OPEN', message: '일정이 끝나면 투표할 수 있어요.', details: [] }))
    renderPage()
    expect(await screen.findByText('일정이 끝나면 투표할 수 있어요')).toBeInTheDocument()
    expect(screen.queryByText('우리 팀에서')).not.toBeInTheDocument()
  })

  it('이미 제출했으면 완료 화면을 보여준다', async () => {
    vi.mocked(peerApi.targets).mockResolvedValue({ ...targets, already_submitted: true, my_votes: [{ target_player_id: 2, vote_type: 'PLAY_AGAIN', reason_tag: 'PASS' }] })
    renderPage()
    expect(await screen.findByText('투표를 마쳤어요')).toBeInTheDocument()
    const card = screen.getByText('서장훈').closest('div')!
    expect(within(card).getByText('패스가 좋았어요')).toBeInTheDocument()
  })
})
