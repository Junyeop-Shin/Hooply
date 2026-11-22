/**
 * 하단 메뉴 (docs/11 규칙 6 · docs/10 X-1) — 홈 · 팀 · 프로필. "팀"은 기본 팀으로 바로 간다.
 * 전에는 홈 · 프로필뿐이라 팀 화면에 가려면 홈을 내려 "내 팀" 카드를 눌러야 했다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TeamMembershipView, UserDetail } from '../api/types'

vi.mock('../api/auth', async (importOriginal) => ({ ...(await importOriginal<typeof import('../api/auth')>()), authApi: { me: vi.fn(), myTeams: vi.fn() } }))

import { authApi } from '../api/auth'
import { TabBar } from './layout'

const team = (id: number) => ({ team_id: id, team_name: `팀${id}`, role: 'PLAYER' } as TeamMembershipView)
const me = (primary: number | null) => ({ id: 1, name: '민수', primary_team_id: primary } as UserDetail)

function renderBar(path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}><TabBar /></MemoryRouter></QueryClientProvider>)
}
const hrefOf = (name: string) => screen.getByRole('link', { name }).getAttribute('href')

describe('TabBar', () => {
  beforeEach(() => {
    vi.mocked(authApi.me).mockReset().mockResolvedValue(me(5))
    vi.mocked(authApi.myTeams).mockReset().mockResolvedValue({ items: [team(3), team(5)] })
  })

  it('홈 · 팀 · 프로필 세 칸이고, 팀은 기본 팀으로 간다', async () => {
    renderBar()
    expect(screen.getAllByRole('link').map((a) => a.textContent)).toEqual(['홈', '팀', '프로필'])
    expect(hrefOf('홈')).toBe('/')
    expect(hrefOf('프로필')).toBe('/me')
    await waitFor(() => expect(hrefOf('팀')).toBe('/teams/5'))
  })

  it('기본 팀을 정하지 않았으면 첫 팀으로 간다', async () => {
    vi.mocked(authApi.me).mockResolvedValue(me(null))
    renderBar()
    await waitFor(() => expect(hrefOf('팀')).toBe('/teams/3'))
  })

  it('팀이 없으면 팀 코드로 가입하는 화면으로 간다', async () => {
    vi.mocked(authApi.myTeams).mockResolvedValue({ items: [] })
    renderBar()
    await waitFor(() => expect(authApi.myTeams).toHaveBeenCalled())
    expect(hrefOf('팀')).toBe('/teams/join')
  })

  it('팀 화면 안에 있으면 팀 칸이 지금 위치로 표시된다', async () => {
    renderBar('/teams/5/leaderboard')
    await waitFor(() => expect(screen.getByRole('link', { name: '팀' })).toHaveAttribute('aria-current', 'page'))
    expect(screen.getByRole('link', { name: '홈' })).not.toHaveAttribute('aria-current')
  })

  it('기본 팀이 아닌 팀의 화면에서도 팀 칸이 켜지고, 누르면 기본 팀으로 간다', async () => {
    renderBar('/teams/3')  // 기본 팀은 5
    await waitFor(() => expect(hrefOf('팀')).toBe('/teams/5'))
    expect(screen.getByRole('link', { name: '팀' })).toHaveAttribute('aria-current', 'page')
  })

  it('홈과 프로필은 그 화면에서만 켜진다', () => {
    renderBar('/me')
    expect(screen.getByRole('link', { name: '프로필' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '홈' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('link', { name: '팀' })).not.toHaveAttribute('aria-current')
  })
})
