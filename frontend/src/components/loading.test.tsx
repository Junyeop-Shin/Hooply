/** 로딩 표시 두 층 — 섹션은 그 자리에 작은 링, 화면 전체는 덮개, 5초를 넘기면 어느 쪽이든 덮개와 기다림 문구 하나 */
import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SLOW_AFTER_MS, WAIT_MESSAGES, WAIT_SUBLINE } from '../lib/wait-messages'
import { resetLoadingForTest } from '../store/loading'
import { LoadingHost } from './loading'
import { Sheet, Spinner } from './ui'

const overlay = () => document.querySelector('.fixed.inset-0.z-20')

describe('로딩 표시', () => {
  beforeEach(() => { vi.useFakeTimers(); resetLoadingForTest() })
  afterEach(() => { vi.useRealTimers() })

  it('섹션 로딩은 그 자리에 작은 링만 — 전체 덮개는 없다', () => {
    const { container } = render(<><Spinner /><LoadingHost /></>)
    expect(container.querySelector('.size-6.animate-spin')).toBeInTheDocument()
    expect(overlay()).toBeNull()
  })

  it('화면 전체 로딩은 덮개 하나 — 문구는 5초 뒤에', () => {
    render(<><Spinner page /><LoadingHost /></>)
    expect(overlay()).toBeInTheDocument()
    expect(overlay()!.className).toContain('backdrop-blur')
    expect(screen.queryByRole('status')).toBeNull()
    act(() => { vi.advanceTimersByTime(SLOW_AFTER_MS) })
    const status = screen.getByRole('status')
    expect(WAIT_MESSAGES.some((m) => status.textContent!.includes(m))).toBe(true)
    expect(status.textContent).toContain(WAIT_SUBLINE)
  })

  it('섹션 로딩이 5초를 넘기면 덮개와 문구가 넘겨받고 섹션 링은 숨는다 (로딩 표시 하나만)', () => {
    const { container } = render(<><Spinner /><Spinner /><LoadingHost /></>)
    expect(overlay()).toBeNull()
    act(() => { vi.advanceTimersByTime(SLOW_AFTER_MS) })
    expect(overlay()).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
    container.querySelectorAll('.size-6.animate-spin').forEach((el) => expect(el.className).toContain('invisible'))
  })

  it('로딩이 끝나면 덮개와 문구가 사라지고 다음 로딩은 다시 5초부터 센다', () => {
    const { rerender } = render(<><Spinner page /><LoadingHost /></>)
    act(() => { vi.advanceTimersByTime(SLOW_AFTER_MS) })
    expect(screen.getByRole('status')).toBeInTheDocument()
    rerender(<LoadingHost />)
    expect(overlay()).toBeNull()
    rerender(<><Spinner page /><LoadingHost /></>)
    act(() => { vi.advanceTimersByTime(SLOW_AFTER_MS - 1) })
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('시트가 열려 있으면 흐림 덮개 없이 링만 (시트 뒤를 두 겹으로 어둡게 하지 않는다)', () => {
    render(<><Spinner page /><Sheet label="시험" title="시험" onClose={() => {}}><p>내용</p></Sheet><LoadingHost /></>)
    expect(overlay()).toBeInTheDocument()
    expect(overlay()!.className).not.toContain('backdrop-blur')
  })
})
