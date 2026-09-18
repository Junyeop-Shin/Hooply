import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from './ErrorBoundary'

function Boom(): never {
  throw new Error('테스트용 오류')
}

describe('ErrorBoundary', () => {
  it('자식이 오류를 던지면 안내와 새로고침 버튼을 보여 준다', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ErrorBoundary><Boom /></ErrorBoundary>)
    expect(screen.getByText('화면을 불러오지 못했어요')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '새로고침' })).toBeInTheDocument()
    expect(screen.getByText('테스트용 오류')).toBeInTheDocument()
  })

  it('오류가 없으면 자식을 그대로 그린다', () => {
    render(<ErrorBoundary><p>정상</p></ErrorBoundary>)
    expect(screen.getByText('정상')).toBeInTheDocument()
  })
})
