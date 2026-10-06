/** Avatar — 사진이 있으면 사진, 없거나 불러오지 못하면 이름 첫 글자 (카카오 CDN 주소는 만료될 수 있다) */
import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { describe, expect, it } from 'vitest'
import { Avatar } from './ui'

describe('Avatar', () => {
  it('사진이 없으면 이름 첫 글자를 보여준다', () => {
    render(<Avatar name="허재" />)
    expect(screen.getByText('허')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('사진이 있으면 이미지를 보여주고, 상대 주소는 그대로 쓴다', () => {
    render(<Avatar name="허재" src="/api/v1/users/1/avatar?v=abc" />)
    const img = screen.getByRole('presentation', { hidden: true }) as HTMLImageElement
    expect(img.getAttribute('src')).toBe('/api/v1/users/1/avatar?v=abc')  // VITE_API_URL 이 없으면 같은 도메인
  })

  it('사진을 불러오지 못하면 이름 첫 글자로 돌아간다', () => {
    render(<Avatar name="서장훈" src="/api/v1/users/9/avatar?v=zzz" />)
    fireEvent.error(screen.getByRole('presentation', { hidden: true }))
    expect(screen.getByText('서')).toBeInTheDocument()
  })
})

describe('Avatar — 주소가 바뀌면 다시 시도한다 (사진을 새로 올린 경우)', () => {
  it('실패한 뒤 src 가 바뀌면 이미지를 다시 그린다', () => {
    const { rerender } = render(<Avatar name="서장훈" src="/api/v1/users/9/avatar?v=old" />)
    fireEvent.error(screen.getByRole('presentation', { hidden: true }))
    expect(screen.getByText('서')).toBeInTheDocument()
    rerender(<Avatar name="서장훈" src="/api/v1/users/9/avatar?v=new" />)
    expect(screen.getByRole('presentation', { hidden: true }).getAttribute('src')).toBe('/api/v1/users/9/avatar?v=new')
  })
})
