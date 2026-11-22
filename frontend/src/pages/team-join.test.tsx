/**
 * S-06 팀 가입 뒤 어디로 가나 (docs/10 F-3) — 초대 링크로 온 새 팀원이 설문 12문항보다 먼저 가입 · 응답까지 가게 한다.
 * - 설문을 아직 안 한 사람: "내 위치" 문항을 건너뛰고(설문 전에는 쓰이지 않는다) 응답을 받는 가장 가까운 일정으로, 없으면 팀 화면으로
 * - 설문을 한 사람(두 번째 팀에 가입): 전처럼 "내 위치" 문항으로
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { localISODate, type EventView, type Page, type TeamDetail, type UserDetail } from '../api/types'

vi.mock('../api/auth', async (importOriginal) => ({ ...(await importOriginal<typeof import('../api/auth')>()), authApi: { me: vi.fn(), myTeams: vi.fn() } }))
vi.mock('../api/teams', () => ({ teamsApi: { join: vi.fn() } }))
vi.mock('../api/events', () => ({ eventsApi: { list: vi.fn() } }))

import { authApi } from '../api/auth'
import { eventsApi } from '../api/events'
import { teamsApi } from '../api/teams'
import { TeamJoinPage } from './team'

const day = (plus: number) => localISODate(new Date(Date.now() + plus * 86_400_000))
const event = (over: Partial<EventView>): EventView => ({ id: 12, team_id: 3, title: '일요 정기전', event_date: day(7), start_time: '10:00:00', end_time: '12:00:00', status: 'OPEN', rsvp_open: true, ...over } as EventView)
const page = (items: EventView[]): Page<EventView> => ({ items, meta: { page: 1, size: 50, total: items.length, has_next: false } })
const me = (onboarded: boolean) => ({ id: 1, name: '민수', nickname: null, onboarding_completed: onboarded } as UserDetail)

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

async function join() {
  window.history.replaceState(null, '', '/teams/join?code=CTMATE26')  // 초대 링크 — 화면이 주소의 code 를 읽어 칸을 채운다
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/teams/join?code=CTMATE26']}>
        <Routes>
          <Route path="/teams/join" element={<TeamJoinPage />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(screen.getByLabelText('팀 코드')).toHaveValue('CTMATE26')
  await userEvent.click(screen.getByRole('button', { name: '가입하기' }))
  return screen.findByTestId('where')
}

describe('TeamJoinPage — 가입한 뒤', () => {
  beforeEach(() => {
    vi.mocked(teamsApi.join).mockReset().mockResolvedValue({ id: 3, name: '일요 코트메이트' } as TeamDetail)
    vi.mocked(eventsApi.list).mockReset().mockResolvedValue(page([]))
    vi.mocked(authApi.me).mockReset().mockResolvedValue(me(false))
  })
  afterEach(() => window.history.replaceState(null, '', '/'))

  it('설문을 안 한 사람은 내 위치 문항을 건너뛰고, 응답을 받는 가장 가까운 일정으로 간다', async () => {
    vi.mocked(eventsApi.list).mockResolvedValue(page([
      event({ id: 11, event_date: day(0), status: 'CLOSED', rsvp_open: false }),  // 오늘 일정은 이미 마감
      event({ id: 13, event_date: day(14) }),
      event({ id: 12, event_date: day(7) }),
    ]))
    expect(await join()).toHaveTextContent('/events/12')
    expect(teamsApi.join).toHaveBeenCalledWith('CTMATE26')
  })

  it('설문을 안 한 사람인데 응답을 받는 일정이 없으면 팀 화면으로 간다', async () => {
    vi.mocked(eventsApi.list).mockResolvedValue(page([event({ id: 11, event_date: day(0), status: 'CLOSED', rsvp_open: false })]))
    expect(await join()).toHaveTextContent(/^\/teams\/3$/)
  })

  it('일정을 못 받아도 가입은 끝났으니 팀 화면으로 간다', async () => {
    vi.mocked(eventsApi.list).mockRejectedValue(new Error('offline'))
    expect(await join()).toHaveTextContent(/^\/teams\/3$/)
  })

  it('설문을 한 사람은 전처럼 내 위치 문항으로 간다', async () => {
    vi.mocked(authApi.me).mockResolvedValue(me(true))
    expect(await join()).toHaveTextContent('/teams/3/self-rank')
    expect(eventsApi.list).not.toHaveBeenCalled()
  })
})
