/**
 * 기록 표시 조각 — 선수 상세(S-08)와 내 프로필(S-17)이 함께 쓴다.
 * 두 화면이 서로를 import 하면 한 화면만 열어도 다른 화면 코드까지 내려받게 되므로 여기로 뺐다.
 */
import { useState, type ReactNode } from 'react'
import type { MarginPoint, QuarterRecord } from '../api/types'
import { squadName, squadStyle } from '../lib/squads'
import { Card } from './ui'

/** 회차별 평균 마진 막대 (0 기준 좌우). 실력 지표가 아니라 그 회차의 결과라는 점을 라벨로 명시 */
export function MarginTrend({ points }: { points: MarginPoint[] }) {
  if (points.length === 0) return <Card><p className="text-sm text-faint">매니저가 경기 뒤에 기록하면 여기에 보여요.</p></Card>
  const max = Math.max(3, ...points.map((m) => Math.abs(Number(m.avg_normalized_margin))))
  return (
    <Card className="space-y-1.5">
      <p className="text-[11px] text-faint">일정마다 뛴 쿼터의 평균 점수 차예요. 팀 결과라서 개인 실력 그 자체는 아니에요.</p>
      {points.map((m) => {
        const v = Number(m.avg_normalized_margin)
        const w = Math.round((Math.abs(v) / max) * 50)
        return (
          <div key={m.event_id} className="flex items-center gap-2 text-xs">
            <span className="w-12 shrink-0 text-muted">{m.event_date.slice(5).split('-').map(Number).join('/')}</span>
            <div className="relative h-4 flex-1 rounded bg-sunken">
              <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
              <div className={`absolute inset-y-0.5 rounded ${v >= 0 ? 'left-1/2 bg-ok-ink' : 'right-1/2 bg-danger-ink'}`} style={{ width: `${Math.max(w, v === 0 ? 0 : 2)}%` }} />
            </div>
            <span className={`w-12 shrink-0 text-right font-semibold ${v > 0 ? 'text-ok-ink' : v < 0 ? 'text-danger-ink' : 'text-muted'}`}>{v > 0 ? '+' : ''}{v.toFixed(1)}</span>
            <span className="w-12 shrink-0 whitespace-nowrap text-right text-faint">{m.wins}승 {m.losses}패</span>
          </div>
        )
      })}
    </Card>
  )
}

const PAGE = 10

/** 목록을 10개씩 끊어 카드 안에서 페이지 이동 (최신순 목록 기준: ‹ 최근 / 이전 ›) */
export function Paged<T>({ items, render, unit = '개' }: { items: T[]; render: (item: T, i: number) => ReactNode; unit?: string }) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(items.length / PAGE))
  const cur = Math.min(page, pages - 1)
  return (
    <Card className="divide-y divide-line p-0">
      {pages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 text-xs">
          <button disabled={cur === 0} onClick={() => setPage(cur - 1)} className="-my-2 min-h-11 rounded-lg px-2 font-semibold text-ink-2 disabled:opacity-30">‹ 최근</button>
          <span className="text-muted">{cur * PAGE + 1}–{Math.min(items.length, (cur + 1) * PAGE)} / {items.length}{unit}</span>
          <button disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} className="-my-2 min-h-11 rounded-lg px-2 font-semibold text-ink-2 disabled:opacity-30">이전 ›</button>
        </div>
      )}
      {items.slice(cur * PAGE, cur * PAGE + PAGE).map((it, i) => render(it, cur * PAGE + i))}
    </Card>
  )
}

/** 내가 뛴 팀 번호 — 서버가 squad_no 를 주지 않으면(예전 응답) 칸으로 */
const squadOf = (r: Pick<QuarterRecord, 'side' | 'squad_no'>) => r.squad_no ?? (r.side === 'BLACK' ? 1 : 2)

/** 쿼터 기록 목록 — 10개씩 페이지 이동. 이긴 쿼터는 초록, 진 쿼터는 로즈 배지 */
export function QuarterList({ records }: { records: QuarterRecord[] }) {
  if (records.length === 0) return null
  return (
    <Paged items={records} unit="쿼터" render={(r) => {
        const win = r.raw_margin > 0
        return (
          <div key={`${r.event_id}-${r.quarter_no}`} className="flex items-center gap-3 px-4 py-2 text-xs">
            <span className="w-12 shrink-0 text-muted">{r.event_date.slice(5).split('-').map(Number).join('/')}</span>
            <span className="w-10 shrink-0 font-semibold text-ink">{r.quarter_no}쿼터</span>
            {/* 칸(side)이 아니라 내가 뛴 팀 — 3팀인 날 레드가 블랙 · 화이트 칸에 설 수 있다 */}
            <span className={`inline-flex w-12 shrink-0 items-center justify-center rounded-full border py-0.5 text-[10px] font-semibold ${squadStyle(squadOf(r)).card}`}>{squadName(squadOf(r))}</span>
            <span className="flex-1 text-muted">{r.my_score} : {r.their_score}{r.position ? ` · ${r.position}` : ''}</span>
            {/* 작은 흰 글자라 짙은 색 — emerald-700 5.48:1 · rose-700 6.29:1 */}
            <span className={`inline-flex w-12 shrink-0 items-center justify-center rounded-full py-0.5 text-[11px] font-bold ${win ? 'bg-emerald-700 text-white' : r.raw_margin < 0 ? 'bg-rose-700 text-white' : 'bg-line text-muted'}`}>{r.raw_margin > 0 ? '+' : ''}{r.raw_margin}</span>
          </div>
        )
      }} />
  )
}
