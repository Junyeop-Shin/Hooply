import { describe, expect, it } from 'vitest'
import { moveItem, tapReorder } from './reorder'

describe('moveItem', () => {
  it('위로 · 아래로 옮긴다', () => {
    expect(moveItem(['a', 'b', 'c', 'd'], 3, 0)).toEqual(['d', 'a', 'b', 'c'])
    expect(moveItem(['a', 'b', 'c', 'd'], 0, 2)).toEqual(['b', 'c', 'a', 'd'])
  })
  it('범위를 벗어나면 그대로 (원본은 바꾸지 않는다)', () => {
    const list = ['a', 'b']
    expect(moveItem(list, 0, -1)).toEqual(['a', 'b'])
    expect(moveItem(list, 1, 2)).toEqual(['a', 'b'])
    expect(list).toEqual(['a', 'b'])
  })
})

describe('tapReorder', () => {
  const order = ['허재', '서장훈', '현주엽', '이상민']
  it('누르면 집고, 다른 카드를 누르면 그 자리로 옮긴다', () => {
    const picked = tapReorder({ order, picked: null }, 3)
    expect(picked).toEqual({ order, picked: 3 })
    expect(tapReorder(picked, 0)).toEqual({ order: ['이상민', '허재', '서장훈', '현주엽'], picked: null })
  })
  it('같은 카드를 다시 누르면 내려놓는다', () => {
    expect(tapReorder({ order, picked: 1 }, 1)).toEqual({ order, picked: null })
  })
})
