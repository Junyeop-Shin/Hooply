/**
 * S-19 실력 정렬 (docs/09 3-6) — 지난 정렬 뒤에 들어온 사람은 "아직 순서 없음" 에 따로, 넣은 사람만 저장.
 * 지난 순서를 불러와 다시 저장할 수 있다. API 는 vi.mock 으로 대체한다.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlayerCard, RankingView } from '../api/types'

vi.mock('../api/teams', () => ({ teamsApi: { players: vi.fn() } }))
vi.mock('../api/assignments', () => ({ rankingsApi: { latest: vi.fn(), create: vi.fn(), history: vi.fn() } }))

import { rankingsApi } from '../api/assignments'
import { teamsApi } from '../api/teams'
import { RankingPage } from './ranking'

const player = (id: number, name: string): PlayerCard => ({
  id, user_id: id, kind: 'MEMBER', display_name: name, role: 'PLAYER', profile_image_url: null, height_cm: null,
  skill_grade: 'C', primary_position: 'SF', playable_positions: ['SF'], attendance_rate: null, skill_confidence: null,
})
const [a, b, c, newbie] = [player(1, '가'), player(2, '나'), player(3, '다'), player(4, '새사람')]
const version = (id: number, ids: PlayerCard[], active: boolean, at: string): RankingView => ({
  id, ranked_at: at, ranked_by: 1, is_active: active, entries: ids.map((p, i) => ({ rank_no: i + 1, player: p })),
})

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/teams/1/ranking']}>
        <Routes>
          <Route path="/teams/:teamId/ranking" element={<RankingPage />} />
          <Route path="*" element={<p>나감</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RankingPage — 새로 온 사람과 지난 순서', () => {
  beforeEach(() => {
    vi.mocked(teamsApi.players).mockResolvedValue({ items: [a, b, c, newbie] } as never)
    const active = version(2, [b, a, c], true, '2026-11-10T10:00:00Z')
    vi.mocked(rankingsApi.latest).mockResolvedValue(active)
    vi.mocked(rankingsApi.history).mockResolvedValue({ items: [active, version(1, [a, b, c], false, '2026-10-01T10:00:00Z')] })
    vi.mocked(rankingsApi.create).mockResolvedValue(active)
  })

  it('새로 온 사람은 따로 두고, 넣지 않으면 저장에서 뺀다', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(await screen.findByText('아직 순서 없음 1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '이 순서로 저장' }))
    await waitFor(() => expect(rankingsApi.create).toHaveBeenCalledWith(1, [2, 1, 3]))
  })

  it('순서에 넣으면 맨 아래로 들어가 함께 저장된다', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '순서에 넣기' }))
    expect(screen.queryByText(/아직 순서 없음/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '4위 새사람 집기' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '이 순서로 저장' }))
    await waitFor(() => expect(rankingsApi.create).toHaveBeenCalledWith(1, [2, 1, 3, 4]))
  })

  it('지난 순서를 불러와 저장할 수 있다', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: '10/1 순서' }))
    expect(screen.getByRole('button', { name: '1위 가 집기' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '이 순서로 저장' }))
    await waitFor(() => expect(rankingsApi.create).toHaveBeenCalledWith(1, [1, 2, 3]))
  })
})
