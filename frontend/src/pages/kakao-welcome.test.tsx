/**
 * 카카오 로그인 콜백 (docs/09 3-1 · 3-2 · 3-3) — 카카오 응답은 vi.mock 으로 대체한다.
 * - 처음 온 사람: 팀에 보일 이름을 정하고(닉네임은 비워 이 이름이 보이게), 초대 링크로 왔으면 설문으로
 * - "이메일 계정이 있어요": 방금 만든 계정을 지우고 로그인 화면에서 카카오 연결을 안내
 * - 원래 있던 사람: 맡겨 둔 주소(초대 링크)로 바로
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UserDetail } from '../api/types'

vi.mock('../api/auth', () => ({ authApi: { kakaoCallback: vi.fn(), me: vi.fn(), updateMe: vi.fn(), deleteMe: vi.fn() } }))

import { authApi } from '../api/auth'
import { saveReturnTo } from '../lib/return-to'
import { KakaoCallbackPage } from './auth'

const pair = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{loc.pathname + loc.search}{(loc.state as { notice?: string } | null)?.notice ?? ''}</p>
}

function renderCallback() {
  sessionStorage.setItem('kakao_state', 'st')
  return render(
    <MemoryRouter initialEntries={['/auth/kakao/callback?code=c&state=st']}>
      <Routes>
        <Route path="/auth/kakao/callback" element={<KakaoCallbackPage />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('KakaoCallbackPage', () => {
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear()
    window.history.replaceState(null, '', '/auth/kakao/callback?code=c&state=st')
    vi.mocked(authApi.me).mockResolvedValue({ id: 1, name: '민수🏀', nickname: '민수🏀' } as UserDetail)
    vi.mocked(authApi.updateMe).mockResolvedValue({ id: 1 } as UserDetail)
    vi.mocked(authApi.deleteMe).mockResolvedValue(undefined)
  })

  it('처음 온 사람은 팀에 보일 이름을 정하고, 초대 링크로 왔으면 설문으로 간다', async () => {
    vi.mocked(authApi.kakaoCallback).mockResolvedValue({ ...pair, is_new: true })
    saveReturnTo('/teams/join?code=CTMATE26')
    const user = userEvent.setup()
    renderCallback()
    const field = await screen.findByLabelText('팀에 보일 이름')
    expect(field).toHaveValue('민수🏀')
    await user.clear(field)
    await user.type(field, '김민수')
    await user.click(screen.getByRole('button', { name: '이 이름으로 시작하기' }))
    expect(authApi.updateMe).toHaveBeenCalledWith({ name: '김민수', nickname: null })
    expect(await screen.findByTestId('where')).toHaveTextContent('/survey')
  })

  it('이메일 계정이 있으면 방금 만든 계정을 지우고 로그인 화면에서 카카오 연결을 안내한다', async () => {
    vi.mocked(authApi.kakaoCallback).mockResolvedValue({ ...pair, is_new: true })
    const user = userEvent.setup()
    renderCallback()
    await user.click(await screen.findByRole('button', { name: '이메일 계정이 있어요' }))
    expect(authApi.deleteMe).toHaveBeenCalled()
    const where = await screen.findByTestId('where')
    expect(where).toHaveTextContent('/login')
    expect(where).toHaveTextContent('카카오 연결')
  })

  it('원래 있던 사람은 맡겨 둔 초대 링크로 바로 간다', async () => {
    vi.mocked(authApi.kakaoCallback).mockResolvedValue({ ...pair, is_new: false })
    saveReturnTo('/teams/join?code=CTMATE26')
    renderCallback()
    expect(await screen.findByTestId('where')).toHaveTextContent('/teams/join?code=CTMATE26')
    expect(authApi.updateMe).not.toHaveBeenCalled()
  })
})
