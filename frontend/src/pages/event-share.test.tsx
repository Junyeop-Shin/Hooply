/**
 * S-10 일정 알리기 (docs/10 F-1) — 매니저가 응답을 받는 일정을 카카오톡으로 알린다.
 * 문구는 화면이 이미 받은 값으로 만들고(lib/event-share), 보내기는 다른 공유와 같은 길(lib/kakao)을 쓴다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AttendanceList, AttendanceStatus, AttendanceView, EventView, PlayerCard, UserDetail } from '../api/types'

vi.mock('../api/auth', async (importOriginal) => ({ ...(await importOriginal<typeof import('../api/auth')>()), authApi: { me: vi.fn() } }))
vi.mock('../api/events', () => ({ eventsApi: { get: vi.fn(), attendances: vi.fn() } }))
vi.mock('../lib/kakao', async (importOriginal) => ({ ...(await importOriginal<typeof import('../lib/kakao')>()), shareText: vi.fn(), announceShare: vi.fn() }))

import { authApi } from '../api/auth'
import { eventsApi } from '../api/events'
import { announceShare, shareText } from '../lib/kakao'
import { EventDetailPage } from './events'

const event = (over: Partial<EventView> = {}): EventView => ({
  id: 7, team_id: 1, title: '일요 정기전', event_date: '2026-11-29', start_time: '10:00:00', end_time: '12:00:00',
  venue: '서초 사회체육관', rsvp_deadline: null, status: 'OPEN', memo: null, attend_count: 3, my_attendance: 'ATTEND', rsvp_open: true,
  my_role: 'MANAGER', adopted_candidate_id: null, run_count: 0, my_squad_name: null, my_assigned_position: null, quarter_count: 0,
  survey_open: false, my_survey_submitted: false, survey_responded: 0, survey_total: 0, ...over,
})
const row = (id: number, status: AttendanceStatus, kind: 'MEMBER' | 'GUEST' = 'MEMBER'): AttendanceView => ({
  player: {
    id, user_id: kind === 'MEMBER' ? id : null, kind, display_name: kind === 'MEMBER' ? `선수${id}` : `게스트${id}`, role: 'PLAYER', profile_image_url: null,
    height_cm: null, skill_grade: null, primary_position: 'SF', playable_positions: ['SF'], attendance_rate: null, skill_confidence: null,
  } as PlayerCard,
  status, note: null, responded_at: null, registered_by: null, registered_by_name: null,
  team_lock_request_player_id: null, team_lock_request_player_name: null, can_edit: false,
})
const attendances: AttendanceList = {
  items: [row(1, 'ATTEND'), row(2, 'ATTEND'), row(3, 'PENDING'), row(4, 'PENDING'), row(9, 'ATTEND', 'GUEST')],
  summary: { attend: 3, absent: 0, pending: 2, guest_count: 1, position_counts: { PG: 0, SG: 0, SF: 5, PF: 0, C: 0 }, handler_count: 0, bigman_count: 0, warnings: [] },
  my_player_id: 1,
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/events/7']}>
        <Routes><Route path="/events/:eventId" element={<EventDetailPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('EventDetailPage — 일정 알리기', () => {
  beforeEach(() => {
    vi.mocked(shareText).mockReset().mockResolvedValue('clipboard')
    vi.mocked(announceShare).mockReset()
    vi.mocked(eventsApi.get).mockResolvedValue(event())
    vi.mocked(eventsApi.attendances).mockResolvedValue(attendances)
    vi.mocked(authApi.me).mockResolvedValue({ id: 1, name: '허재', onboarding_completed: true } as UserDetail)
  })

  // 설문보다 가입 · 응답을 먼저 하게 됐으므로(docs/10 F-3), 응답하는 자리에서 설문을 한 번 권한다
  it('설문을 안 한 사람에게는 응답 아래에 설문 안내가 보인다', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ id: 1, name: '민수', onboarding_completed: false } as UserDetail)
    vi.mocked(eventsApi.get).mockResolvedValue(event({ my_role: 'PLAYER' }))
    renderPage()
    expect(await screen.findByRole('link', { name: /실력 설문/ })).toHaveAttribute('href', '/survey')
  })

  it('설문을 한 사람에게는 설문 안내가 없다', async () => {
    renderPage()
    await screen.findByText('미응답 2')
    expect(screen.queryByRole('link', { name: /실력 설문/ })).toBeNull()
  })

  it('끝난 일정에는 설문을 안 한 사람에게도 설문 안내가 없다', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ id: 1, name: '민수', onboarding_completed: false } as UserDetail)
    vi.mocked(eventsApi.get).mockResolvedValue(event({ my_role: 'PLAYER', status: 'DONE', rsvp_open: false, survey_open: true, quarter_count: 8 }))
    renderPage()
    await screen.findByText('미응답 2')
    expect(screen.queryByRole('link', { name: /실력 설문/ })).toBeNull()
  })

  it('매니저가 누르면 날짜 · 응답 현황 · 아직 응답 안 한 팀원 이름과 일정 주소를 보낸다', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '카카오톡으로 일정 알리기' }))
    await waitFor(() => expect(shareText).toHaveBeenCalledTimes(1))
    const [text, url] = vi.mocked(shareText).mock.calls[0]
    expect(text).toContain('[HOOPLY] 일요 정기전 · 11/29 (일) 10:00~12:00')
    expect(text).toContain('참석 3명 · 미응답 2명')  // 참석에는 게스트도 센다
    expect(text).toContain('아직 응답 안 한 분: 선수3, 선수4')  // 이름은 팀원만 — 게스트는 응답할 일이 없다
    expect(url).toMatch(/\/events\/7$/)
    await waitFor(() => expect(announceShare).toHaveBeenCalledWith('clipboard'))  // 결과는 다른 공유처럼 토스트로
    expect(screen.getByText('아직 응답 안 한 2명의 이름도 함께 보내요.')).toBeInTheDocument()  // 무엇이 나가는지 미리 알린다
  })

  it('팀원에게는 알리기 버튼이 없다', async () => {
    vi.mocked(eventsApi.get).mockResolvedValue(event({ my_role: 'PLAYER' }))
    renderPage()
    await screen.findByText('이번 일정, 참석하시나요?')
    await screen.findByText('미응답 2')
    expect(screen.queryByRole('button', { name: '카카오톡으로 일정 알리기' })).toBeNull()
  })

  it('응답을 마감한 일정에는 알리기 버튼이 없다', async () => {
    vi.mocked(eventsApi.get).mockResolvedValue(event({ status: 'CLOSED', rsvp_open: false }))
    renderPage()
    await screen.findByText('미응답 2')
    expect(screen.queryByRole('button', { name: '카카오톡으로 일정 알리기' })).toBeNull()
  })
})
