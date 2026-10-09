import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Play } from '../api/types'
import { TacticBoard } from './tactic-board'

const P = (x: number, y: number) => ({ x, y })
const play: Play = {
  key: 'test', name: '테스트', summary: '', defense: 'man', situation: 'half_court', counter: '', opp_defense: 'man', screen_call: 'stay',
  start: [P(0.5, 0.66), P(0.95, 0.05), P(0.05, 0.05), P(0.15, 0.48), P(0.66, 0.42)],
  ball: 1,
  roles: ['ball_handler', 'shooter', 'shooter', 'spacer', 'screener_roll'],
  steps: [
    { caption: '스크린', actions: [{ type: 'screen', slot: 5, to: P(0.57, 0.63), target: 1 }] },
    { caption: '패스', actions: [{ type: 'pass', slot: 1, to: null, target: 5 }] },
    { caption: '슛', actions: [{ type: 'shot', slot: 5, to: null, target: null }] },
  ],
}

describe('TacticBoard 재생', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('첫 프레임 시각이 재생을 누른 시각보다 일러도 깨지지 않는다 (휴대폰 브라우저의 rAF 시각)', () => {
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => frames.push(cb))
    vi.stubGlobal('cancelAnimationFrame', () => {})
    render(<TacticBoard play={play} />)
    fireEvent.click(screen.getByRole('button', { name: '재생' }))
    // rAF 는 그 프레임의 시작 시각을 준다 — 클릭 처리 중에 잰 performance.now() 보다 이를 수 있다
    act(() => { frames.shift()!(performance.now() - 8) })
    expect(screen.getByText('1/3')).toBeInTheDocument()
    act(() => { frames.shift()!(performance.now() + 5000) })
    expect(screen.queryByText('화면을 불러오지 못했어요')).toBeNull()
  })

  it('자리를 바꿀 수 있는 전술판은 키보드로도 자리를 고른다', () => {
    const onSlotTap = vi.fn()
    render(<TacticBoard play={play} names={['허재', null, null, null, null]} onSlotTap={onSlotTap} />)
    const slot = screen.getByRole('button', { name: '1번 자리 허재, 사람 바꾸기' })
    expect(slot).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(slot, { key: 'Enter' })
    expect(onSlotTap).toHaveBeenCalledWith(1)
  })

  it('다음 단계 버튼으로 한 단계씩 넘어간다', () => {
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => frames.push(cb))
    vi.stubGlobal('cancelAnimationFrame', () => {})
    render(<TacticBoard play={play} />)
    fireEvent.click(screen.getByRole('button', { name: '다음 단계' }))
    act(() => { frames.shift()!(performance.now() + 5000) })
    expect(screen.getByText('2/3').parentElement).toHaveTextContent('2/3패스')
  })
})
