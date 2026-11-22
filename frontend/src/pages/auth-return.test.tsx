/**
 * 이메일로 로그인 · 가입한 직후 맡겨 둔 주소(초대 · 투표 링크)로 가서 **그대로 머무는지** (FR-01, docs/09 3-1 · docs/10 F-3).
 * 전에는 화면이 그 주소로 보낸 직후, 로그인 화면을 감싼 가드(GuestOnly)의 "로그인했으면 홈으로"가 뒤늦게 실행돼 홈으로 덮어썼다 —
 * 주소는 이미 꺼내 지운 뒤라 초대 링크가 사라졌다. 카카오 로그인은 가드 밖이라 괜찮았다.
 * 그래서 이동은 가드 한 곳에서만 한다. 여기서는 실제 가드와 실제 화면을 함께 올려 확인한다.
 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/auth', async (importOriginal) => ({ ...(await importOriginal<typeof import('../api/auth')>()), authApi: { login: vi.fn(), signup: vi.fn(), kakaoLoginUrl: vi.fn() } }))

import { authApi } from '../api/auth'
import { GuestOnly } from '../App'
import { saveReturnTo } from '../lib/return-to'
import { useAuthStore } from '../store/auth'
import { LoginPage, SignupPage } from './auth'

const pair = { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{loc.pathname + loc.search}</p>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<GuestOnly />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
        </Route>
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
}
/** 뒤늦게 실행되는 이동이 있으면 그것까지 끝나게 한 박자 기다린다 */
const settle = () => act(() => new Promise<void>((r) => setTimeout(r, 80)))

async function login() {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('이메일'), 'm05@demo.com')
  await user.type(screen.getByLabelText('비밀번호'), 'demo1234')
  await user.click(screen.getByRole('button', { name: '로그인' }))
  await screen.findByTestId('where')
  await settle()
  return screen.getByTestId('where')
}

describe('이메일 로그인 · 가입 뒤 맡겨 둔 주소', () => {
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear()
    useAuthStore.setState({ accessToken: null, refreshToken: null })
    vi.mocked(authApi.login).mockReset().mockResolvedValue(pair)
    vi.mocked(authApi.signup).mockReset().mockResolvedValue(pair)
  })

  it('로그인하면 맡겨 둔 초대 링크로 가서 그대로 머문다', async () => {
    saveReturnTo('/teams/join?code=CTMATE26')
    renderAt('/login')
    expect(await login()).toHaveTextContent('/teams/join?code=CTMATE26')
    expect(localStorage.getItem('hooply-return-to')).toBeNull()  // 한 번 쓰고 지운다
  })

  it('맡겨 둔 주소가 없으면 홈으로 간다', async () => {
    renderAt('/login')
    expect(await login()).toHaveTextContent(/^\/$/)
  })

  it('새로 가입해도 맡겨 둔 초대 링크로 가서 그대로 머문다 — 설문보다 가입 · 응답이 먼저다', async () => {
    saveReturnTo('/teams/join?code=CTMATE26')
    renderAt('/signup')
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('이메일'), 'new@example.com')
    await user.type(screen.getByLabelText('비밀번호'), 'newbie-pass-1')
    await user.type(screen.getByLabelText('이름'), '새팀원')
    await user.click(screen.getByRole('button', { name: '가입하기' }))
    await screen.findByTestId('where')
    await settle()
    expect(screen.getByTestId('where')).toHaveTextContent('/teams/join?code=CTMATE26')
  })

  it('이미 로그인한 사람이 로그인 화면을 열면 홈으로 보낸다', async () => {
    useAuthStore.setState({ accessToken: 'a', refreshToken: 'r' })
    renderAt('/login')
    await screen.findByTestId('where')
    await settle()
    expect(screen.getByTestId('where')).toHaveTextContent(/^\/$/)
  })
})
