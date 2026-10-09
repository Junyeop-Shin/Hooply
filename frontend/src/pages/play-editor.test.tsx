/** S-30 전술 편집기 — 코트를 키보드만으로 쓸 수 있는지 (시작 위치는 화살표 키, 목적지는 커서 + Enter). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api/tactics', () => ({
  tacticsApi: {}, tacticStarsApi: {},
  teamPlaysApi: { check: vi.fn().mockResolvedValue({ playable: false, errors: [], roles: null, reasons: null }) },
}))
vi.mock('./home', () => ({ useMe: () => ({ data: { id: 1 }, isLoading: false }) }))

import { PlayEditorPage } from './play-editor'

describe('PlayEditorPage 키보드', () => {
  it('시작 위치를 화살표 키로 옮기고, 동작의 목적지를 커서로 정한다', async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/teams/1/plays/new']}>
          <Routes><Route path="/teams/:teamId/plays/new" element={<PlayEditorPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const slot = (n: number) => within(screen.getByRole('group', { name: '전술 편집 코트' })).getByRole('button', { name: `${n}번` })

    // 시작 위치: 2번(오른쪽 윙)을 Shift+↑ 세 번 → 3점 라인 안쪽. 되돌리기가 켜진다
    slot(2).focus()
    await user.keyboard('{Shift>}{ArrowUp}{ArrowUp}{ArrowUp}{/Shift}')
    expect(screen.getByText('2번 자리를 오른쪽 미들로 옮겼어요.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '↶ 되돌리기' })).toBeEnabled()

    // 1단계: 1번 → 드리블 → 커서를 옮겨 Enter
    await user.click(screen.getByRole('tab', { name: '+ 단계' }))
    slot(1).focus()
    await user.keyboard('{Enter}')
    expect(slot(1)).toHaveAttribute('aria-pressed', 'true')
    screen.getByRole('button', { name: '드리블' }).focus()
    await user.keyboard('{Enter}')
    expect(document.activeElement).toHaveAttribute('aria-label', expect.stringContaining('목적지 커서'))
    await user.keyboard('{ArrowUp}{Enter}')
    expect(screen.getByText('1번 드리블')).toBeInTheDocument()
    expect(document.activeElement).toBe(slot(1))  // 커서가 사라져도 포커스를 잃지 않는다
  })
})
