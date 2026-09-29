/**
 * 확정된 팀 구성을 한 장의 이미지로 만든다 (S-14 → 카카오톡 공유).
 *
 * 단체방에서는 링크보다 이미지가 바로 읽힌다. 서버 없이 브라우저 캔버스로 그리고, 카카오 SDK 의
 * 이미지 업로드 → 피드 메시지로 보낸다 (kakao.ts). 실력 수치·등급은 넣지 않는다 — 플레이어 화면과
 * 같은 공개 범위(FR-24)를 이미지에도 지킨다.
 *
 * 레이아웃(layoutSquadImage)은 순수 함수라 테스트할 수 있고, 그리기(renderSquadImage)만 캔버스를 쓴다.
 */
import { POSITIONS, type Position, type SquadView } from '../api/types'

export const IMAGE_WIDTH = 1080  // 2배 해상도. 카카오톡에서 540px 로 보인다
const PAD = 56
const GAP = 32
const HEADER_H = 216
const SQUAD_HEAD_H = 92
const ROW_H = 66
const SQUAD_PAD = 28
const FOOTER_H = 96
const MIN_ROWS = 5  // 인원이 적어도 두 카드 높이를 맞춘다

export interface SquadImageInput {
  teamName: string
  eventLine: string  // 예: "9/20 (일) 10:00~12:00 · 서초 사회체육관 2층"
  squads: SquadView[]
}

export interface MemberRow { name: string; position: string; guest: boolean }
export interface SquadColumn { title: string; count: number; dark: boolean; tone: 'black' | 'white' | 'red'; x: number; width: number; rows: MemberRow[] }
export interface SquadImageLayout {
  width: number
  height: number
  header: { title: string; subtitle: string; caption: string }
  columns: SquadColumn[]
  cardTop: number
  cardHeight: number
  footer: string
}

const POS_ORDER: Record<string, number> = Object.fromEntries(POSITIONS.map((p, i) => [p, i]))

/** 포지션 순서(PG→C), 같은 포지션이면 이름순. 미배정은 맨 뒤 — 코트 위 배치대로 읽힌다 */
export function memberRows(squad: SquadView): MemberRow[] {
  return [...squad.members]
    .map((m) => ({ name: m.display_name, position: (squad.assigned_positions[m.id] ?? null) as Position | null, guest: m.kind === 'GUEST' }))
    .sort((a, b) => (a.position ? POS_ORDER[a.position] : 99) - (b.position ? POS_ORDER[b.position] : 99) || a.name.localeCompare(b.name, 'ko'))
    .map((r) => ({ ...r, position: r.position ?? '—' }))
}

export function layoutSquadImage(input: SquadImageInput): SquadImageLayout {
  const squads = [...input.squads].sort((a, b) => a.squad_no - b.squad_no)
  const n = Math.max(1, squads.length)
  const colWidth = Math.floor((IMAGE_WIDTH - PAD * 2 - GAP * (n - 1)) / n)
  const columns: SquadColumn[] = squads.map((s, i) => ({
    title: `팀 ${s.squad_name}`,
    count: s.members.length,
    dark: s.squad_no !== 2,  // 블랙 · 레드는 어두운 카드
    tone: s.squad_no === 1 ? 'black' : s.squad_no === 3 ? 'red' : 'white',
    x: PAD + i * (colWidth + GAP),
    width: colWidth,
    rows: memberRows(s),
  }))
  const rows = Math.max(MIN_ROWS, ...columns.map((c) => c.rows.length))
  const cardHeight = SQUAD_HEAD_H + rows * ROW_H + SQUAD_PAD
  return {
    width: IMAGE_WIDTH,
    height: HEADER_H + cardHeight + FOOTER_H,
    header: { title: input.teamName, subtitle: input.eventLine, caption: '팀 배정 결과' },
    columns,
    cardTop: HEADER_H,
    cardHeight,
    footer: 'HOOPLY · 실력과 포지션을 맞춰 나눈 팀이에요',
  }
}

const FONT = '-apple-system, "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Pretendard", sans-serif'
const C = {
  bg: '#14213d', headerInk: '#ffffff', headerSub: '#c2cde0', accent: '#f26b1d',
  black: '#111827', blackInk: '#ffffff', blackSub: '#d6d3d1',
  white: '#fafaf9', whiteInk: '#0f1b2d', whiteSub: '#78716c', whiteLine: '#e7e5e4',
  red: '#b91c1c', redSub: '#fecaca',
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

/** 글자가 칸을 넘치면 끝을 … 로 줄인다 */
function ellipsize(ctx: CanvasRenderingContext2D, text: string, max: number): string {
  if (ctx.measureText(text).width <= max) return text
  let t = text
  while (t.length > 1 && ctx.measureText(t + '…').width > max) t = t.slice(0, -1)
  return t + '…'
}

export function drawSquadImage(ctx: CanvasRenderingContext2D, L: SquadImageLayout) {
  ctx.fillStyle = C.bg
  ctx.fillRect(0, 0, L.width, L.height)
  ctx.textBaseline = 'middle'

  // 머리: 팀 이름 · 일정 · 캡션
  ctx.fillStyle = C.accent
  roundRect(ctx, PAD, 52, 14, 44, 4); ctx.fill()
  ctx.fillStyle = C.headerInk
  ctx.font = `800 46px ${FONT}`
  ctx.fillText(ellipsize(ctx, L.header.title, L.width - PAD * 2 - 30), PAD + 30, 74)
  ctx.fillStyle = C.headerSub
  ctx.font = `500 28px ${FONT}`
  ctx.fillText(ellipsize(ctx, L.header.subtitle, L.width - PAD * 2 - 30), PAD + 30, 122)
  ctx.fillStyle = C.accent
  ctx.font = `700 24px ${FONT}`
  ctx.fillText(L.header.caption, PAD + 30, 170)

  for (const col of L.columns) {
    const ink = col.dark ? C.blackInk : C.whiteInk
    const sub = col.tone === 'red' ? C.redSub : col.dark ? C.blackSub : C.whiteSub
    ctx.fillStyle = col.tone === 'red' ? C.red : col.dark ? C.black : C.white
    roundRect(ctx, col.x, L.cardTop, col.width, L.cardHeight, 28); ctx.fill()
    if (!col.dark) { ctx.strokeStyle = C.whiteLine; ctx.lineWidth = 2; ctx.stroke() }

    ctx.fillStyle = ink
    ctx.font = `800 34px ${FONT}`
    ctx.fillText(col.title, col.x + SQUAD_PAD, L.cardTop + 48)
    ctx.fillStyle = sub
    ctx.font = `600 24px ${FONT}`
    const countText = `${col.count}명`
    ctx.fillText(countText, col.x + col.width - SQUAD_PAD - ctx.measureText(countText).width, L.cardTop + 50)

    col.rows.forEach((r, i) => {
      const y = L.cardTop + SQUAD_HEAD_H + i * ROW_H + ROW_H / 2
      ctx.fillStyle = sub
      ctx.font = `700 22px ${FONT}`
      ctx.fillText(r.position, col.x + SQUAD_PAD, y)
      ctx.fillStyle = ink
      ctx.font = `600 30px ${FONT}`
      const nameX = col.x + SQUAD_PAD + 60
      const nameMax = col.width - SQUAD_PAD * 2 - 60 - (r.guest ? 44 : 0)
      const name = ellipsize(ctx, r.name, nameMax)
      ctx.fillText(name, nameX, y)
      if (r.guest) {
        const w = ctx.measureText(name).width
        ctx.fillStyle = sub
        ctx.font = `700 18px ${FONT}`
        ctx.fillText('G', nameX + w + 12, y + 2)
      }
    })
  }

  ctx.fillStyle = C.headerSub
  ctx.font = `600 22px ${FONT}`
  ctx.fillText(L.footer, PAD, L.height - FOOTER_H / 2)
}

/** 레이아웃대로 캔버스에 그려 PNG 파일로 만든다. 브라우저 전용 */
export async function renderSquadImage(input: SquadImageInput, fileName = 'team.png'): Promise<{ file: File; width: number; height: number }> {
  const L = layoutSquadImage(input)
  const canvas = document.createElement('canvas')
  canvas.width = L.width
  canvas.height = L.height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('이미지를 만들지 못했어요.')
  drawSquadImage(ctx, L)
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
  if (!blob) throw new Error('이미지를 만들지 못했어요.')
  return { file: new File([blob], fileName, { type: 'image/png' }), width: L.width, height: L.height }
}
