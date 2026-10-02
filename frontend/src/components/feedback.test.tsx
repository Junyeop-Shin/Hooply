/** 토스트 · 확인 시트 — 기본 alert()/confirm() 대신 쓰는 피드백 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { confirm, toast, useFeedback } from '../store/feedback'
import { ConfirmHost } from './confirm-sheet'
import { ToastHost } from './toast'

const host = () => render(<MemoryRouter><ToastHost /><ConfirmHost /></MemoryRouter>)

describe('피드백', () => {
  afterEach(() => { vi.useRealTimers(); useFeedback.setState({ toasts: [], pending: null }); document.body.style.overflow = '' })

  it('토스트는 같은 문구를 한 번만 띄우고 잠시 뒤 사라진다', () => {
    vi.useFakeTimers()
    host()
    act(() => { toast('복사했어요.'); toast('복사했어요.') })
    expect(screen.getAllByText('복사했어요.')).toHaveLength(1)
    expect(screen.getByRole('status')).toHaveTextContent('복사했어요.')
    act(() => { vi.advanceTimersByTime(3000) })
    expect(screen.queryByText('복사했어요.')).not.toBeInTheDocument()
  })

  it('확인을 누르면 true, Esc 면 false 로 끝나고, 열려 있는 동안 뒤 화면 스크롤을 막는다', async () => {
    const user = userEvent.setup()
    host()
    let ok: Promise<boolean>
    act(() => { ok = confirm({ title: '일정을 삭제할까요?', body: '되돌릴 수 없어요.', confirmLabel: '삭제', danger: true }) })
    const dialog = screen.getByRole('dialog', { name: '일정을 삭제할까요?' })
    expect(dialog).toHaveFocus()
    expect(document.body.style.overflow).toBe('hidden')
    await user.click(screen.getByRole('button', { name: '삭제' }))
    await expect(ok!).resolves.toBe(true)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe('')

    act(() => { ok = confirm({ title: '나갈까요?' }) })
    await user.keyboard('{Escape}')
    await expect(ok!).resolves.toBe(false)
  })

  it('Tab 은 시트 밖으로 나가지 않는다', async () => {
    const user = userEvent.setup()
    host()
    act(() => { void confirm({ title: '마감할까요?', confirmLabel: '마감하기' }) })
    const buttons = screen.getAllByRole('button').filter((b) => screen.getByRole('dialog').contains(b))
    buttons[buttons.length - 1].focus()
    await user.tab()
    expect(buttons[0]).toHaveFocus()
  })
})
