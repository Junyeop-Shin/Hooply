/**
 * S-04 홈에서 바로 참석 · 불참 (docs/10 F-2) — 응답을 받는 다음 일정은 일정 화면까지 가지 않고 홈 카드에서 고른다.
 * 누르면 서버 답을 기다리지 않고 바로 바뀐 것처럼 보이고, 실패하면 원래대로 돌린다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { localISODate, type AttendanceView, type EventView, type Page, type TeamMembershipView, type UserDetail } from '../api/types'

vi.mock('../api/auth', async (importOriginal) => ({ ...(await importOriginal<typeof import('../api/auth')>()), authApi: { me: vi.fn(), myTeams: vi.fn(), updateMe: vi.fn() } }))
vi.mock('../api/events', () => ({ eventsApi: { list: vi.fn(), respond: vi.fn() } }))
vi.mock('../api/teams', () => ({ teamsApi: { myGuestClaims: vi.fn() } }))

import { authApi } from '../api/auth'
import { eventsApi } from '../api/events'
import { teamsApi } from '../api/teams'
import { useFeedback } from '../store/feedback'
import { HomePage } from './home'

const tomorrow = localISODate(new Date(Date.now() + 86_400_000))
const me = { id: 1, email: 'a@b.c', name: '허재', nickname: null, onboarding_completed: true, primary_team_id: 1, tutorial_state: 'DONE', tutorial_path: null, tutorial_tips_seen: [] } as unknown as UserDetail
const team = { team_id: 1, team_name: '일요 코트메이트', team_code: 'CTMATE26', team_status: 'ACTIVE', approval_status: 'APPROVED', player_id: 11, role: 'PLAYER', member_count: 12 } as TeamMembershipView
const event = (over: Partial<EventView> = {}): EventView => ({
  id: 7, team_id: 1, title: '일요 정기전', event_date: tomorrow, start_time: '10:00:00', end_time: '12:00:00', venue: '서초 사회체육관',
  rsvp_deadline: null, status: 'OPEN', memo: null, attend_count: 5, my_attendance: null, rsvp_open: true, my_role: 'PLAYER',
  adopted_candidate_id: null, run_count: 0, my_squad_name: null, my_assigned_position: null, quarter_count: 0,
  survey_open: false, my_survey_submitted: false, survey_responded: 0, survey_total: 0, ...over,
})
const page = (items: EventView[]): Page<EventView> => ({ items, meta: { page: 1, size: 50, total: items.length, has_next: false } })

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter><HomePage /></MemoryRouter></QueryClientProvider>)
}
const rsvp = () => screen.findByRole('group', { name: '참석 응답' })
const pressed = (group: HTMLElement, name: '참석' | '불참') => within(group).getByRole('button', { name }).getAttribute('aria-pressed')

describe('HomePage — 다음 일정에 바로 응답', () => {
  beforeEach(() => {
    useFeedback.setState({ pending: null, toasts: [] })
    vi.mocked(authApi.me).mockResolvedValue(me)
    vi.mocked(authApi.myTeams).mockResolvedValue({ items: [team] })
    vi.mocked(teamsApi.myGuestClaims).mockResolvedValue({ items: [] })
    vi.mocked(eventsApi.list).mockReset().mockResolvedValue(page([event()]))
    vi.mocked(eventsApi.respond).mockReset()
  })

  it('응답을 받는 일정이면 홈에서 참석을 누르고, 서버 답을 기다리지 않고 바로 바뀐다', async () => {
    let answer!: (v: AttendanceView) => void
    vi.mocked(eventsApi.respond).mockReturnValue(new Promise((r) => { answer = r }))
    renderHome()
    const group = await rsvp()
    expect(pressed(group, '참석')).toBe('false')
    expect(pressed(group, '불참')).toBe('false')

    await userEvent.click(within(group).getByRole('button', { name: '참석' }))
    expect(eventsApi.respond).toHaveBeenCalledWith(7, 'ATTEND')
    await waitFor(() => expect(pressed(group, '참석')).toBe('true'))  // 아직 서버는 답하지 않았다

    vi.mocked(eventsApi.list).mockResolvedValue(page([event({ my_attendance: 'ATTEND', attend_count: 6 })]))
    answer({} as AttendanceView)
    await waitFor(() => expect(eventsApi.list).toHaveBeenCalledTimes(2))  // 저장되면 목록을 다시 받는다
    expect(pressed(await rsvp(), '참석')).toBe('true')
  })

  it('이미 응답한 일정은 고른 쪽이 눌려 있고, 다른 쪽을 누르면 바꾼다', async () => {
    vi.mocked(eventsApi.list).mockResolvedValue(page([event({ my_attendance: 'ATTEND' })]))
    vi.mocked(eventsApi.respond).mockResolvedValue({} as AttendanceView)
    renderHome()
    const group = await rsvp()
    expect(pressed(group, '참석')).toBe('true')
    await userEvent.click(within(group).getByRole('button', { name: '참석' }))  // 같은 답을 다시 눌러도 보내지 않는다
    expect(eventsApi.respond).not.toHaveBeenCalled()
    await userEvent.click(within(group).getByRole('button', { name: '불참' }))
    expect(eventsApi.respond).toHaveBeenCalledWith(7, 'ABSENT')
  })

  it('응답이 마감된 일정에는 버튼 없이 상태만 보인다', async () => {
    vi.mocked(eventsApi.list).mockResolvedValue(page([event({ status: 'CLOSED', rsvp_open: false })]))
    renderHome()
    await screen.findByText(/다음 일정/)
    expect(screen.queryByRole('group', { name: '참석 응답' })).toBeNull()
    expect(screen.getByText('응답 마감')).toBeInTheDocument()
  })

  it('설문을 안 한 사람에게도 다음 일정과 응답 버튼이 먼저 보이고, 설문 안내가 함께 보인다 (docs/10 F-3 · X-2)', async () => {
    vi.mocked(authApi.me).mockResolvedValue({ ...me, onboarding_completed: false })
    renderHome()
    expect(await rsvp()).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /실력 설문을 아직 안 하셨어요/ })).toHaveAttribute('href', '/survey')
  })

  // 경기 당일에 막 가입했거나 오늘은 안 가는 사람에게, 응답이 마감된 오늘 경기는 할 일이 없는 일정이다
  it('가장 가까운 일정이 마감됐고 내가 참석자가 아니면, 머리에는 응답을 받는 다음 일정을 올린다', async () => {
    const today = localISODate()
    vi.mocked(eventsApi.list).mockResolvedValue(page([
      event({ id: 5, title: '오늘 경기', event_date: today, status: 'CLOSED', rsvp_open: false, my_attendance: null }),
      event({ id: 7, title: '다음 주 경기' }),
    ]))
    vi.mocked(eventsApi.respond).mockResolvedValue({} as AttendanceView)
    renderHome()
    const group = await rsvp()
    await userEvent.click(within(group).getByRole('button', { name: '참석' }))
    expect(eventsApi.respond).toHaveBeenCalledWith(7, 'ATTEND')
    expect(screen.getByRole('button', { name: '오늘 경기 일정 열기' })).toBeInTheDocument()  // 마감된 오늘 경기는 아래 목록에 남는다
    expect(screen.queryByRole('button', { name: '다음 주 경기 일정 열기' })).toBeNull()  // 머리에 올린 일정을 목록에 또 적지 않는다
  })

  it('오늘 경기에 참석하는 사람에게는 응답이 마감됐어도 오늘 경기를 머리에 올린다', async () => {
    const today = localISODate()
    vi.mocked(eventsApi.list).mockResolvedValue(page([
      event({ id: 5, title: '오늘 경기', event_date: today, status: 'CLOSED', rsvp_open: false, my_attendance: 'ATTEND' }),
      event({ id: 7, title: '다음 주 경기' }),
    ]))
    renderHome()
    expect(await screen.findByText('내 응답 · 참석')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: '참석 응답' })).toBeNull()
    expect(screen.getByRole('button', { name: '다음 주 경기 일정 열기' })).toBeInTheDocument()
  })

  it('응답을 못 보내면 원래대로 돌리고 알린다', async () => {
    vi.mocked(eventsApi.respond).mockRejectedValue(new Error('offline'))
    renderHome()
    const group = await rsvp()
    await userEvent.click(within(group).getByRole('button', { name: '불참' }))
    await waitFor(() => expect(useFeedback.getState().toasts.some((t) => t.kind === 'error')).toBe(true))
    await waitFor(() => expect(pressed(group, '불참')).toBe('false'))
  })
})
