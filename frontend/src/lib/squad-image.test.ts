import { describe, expect, it } from 'vitest'
import type { PlayerCard, SquadView } from '../api/types'
import { IMAGE_WIDTH, layoutSquadImage, memberRows } from './squad-image'

const card = (id: number, name: string, kind: 'MEMBER' | 'GUEST' = 'MEMBER'): PlayerCard => ({
  id, user_id: kind === 'MEMBER' ? id : null, kind, display_name: name, role: 'PLAYER', profile_image_url: null,
  height_cm: null, skill_grade: null, primary_position: null, playable_positions: [], attendance_rate: null, skill_confidence: null,
})
const squad = (no: number, members: PlayerCard[], positions: Record<number, SquadView['assigned_positions'][number]>): SquadView => ({
  squad_no: no, squad_name: no === 1 ? '블랙' : '화이트', avg_skill: null, members, assigned_positions: positions, manual_override_ids: [], avg_height_cm: null,
})

describe('memberRows', () => {
  it('포지션 순서(PG→C)로 놓고, 미배정은 맨 뒤에 둔다', () => {
    const s = squad(1, [card(1, '센터'), card(2, '가드'), card(3, '미정'), card(4, '포워드', 'GUEST')], { 1: 'C', 2: 'PG', 3: null, 4: 'SF' })
    expect(memberRows(s)).toEqual([
      { name: '가드', position: 'PG', guest: false },
      { name: '포워드', position: 'SF', guest: true },
      { name: '센터', position: 'C', guest: false },
      { name: '미정', position: '—', guest: false },
    ])
  })
})

describe('layoutSquadImage', () => {
  const black = squad(1, [card(1, 'a'), card(2, 'b'), card(3, 'c'), card(4, 'd'), card(5, 'e'), card(6, 'f'), card(7, 'g')], {})
  const white = squad(2, [card(11, 'h'), card(12, 'i'), card(13, 'j'), card(14, 'k'), card(15, 'l'), card(16, 'm')], {})

  it('두 팀을 나란히 놓고, 높이는 인원이 많은 쪽에 맞춘다', () => {
    const L = layoutSquadImage({ teamName: '일요 코트메이트', eventLine: '9/20 (일)', squads: [white, black] })
    expect(L.width).toBe(IMAGE_WIDTH)
    expect(L.columns.map((c) => c.title)).toEqual(['팀 블랙', '팀 화이트'])  // squad_no 순
    expect(L.columns[0].dark).toBe(true)
    expect(L.columns[1].x).toBeGreaterThan(L.columns[0].x + L.columns[0].width)
    expect(L.columns[1].x + L.columns[1].width).toBeLessThanOrEqual(IMAGE_WIDTH)
    const small = layoutSquadImage({ teamName: 't', eventLine: '', squads: [squad(1, [card(1, 'a')], {}), squad(2, [card(2, 'b')], {})] })
    expect(L.height).toBeGreaterThan(small.height)  // 7명 > 최소 5행
    expect(L.height).toBeLessThan(IMAGE_WIDTH * 1.5)  // 카카오톡 미리보기에서 잘리지 않는 비율
  })

  it('인원이 적어도 카드가 납작해지지 않게 최소 높이를 지킨다', () => {
    const one = layoutSquadImage({ teamName: 't', eventLine: '', squads: [squad(1, [card(1, 'a')], {}), squad(2, [card(2, 'b')], {})] })
    const five = layoutSquadImage({ teamName: 't', eventLine: '', squads: [black, white].map((s) => ({ ...s, members: s.members.slice(0, 5) }))})
    expect(one.cardHeight).toBe(five.cardHeight)
  })
})
