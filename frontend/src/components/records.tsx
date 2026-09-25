/**
 * 팀 화면 "기록" 탭 — 내 추세(활동일별 꺾은선) · 월간 코트 마진 랭킹(접을 수 있음) · 배지.
 *
 * 순서에 이유가 있다. 추세는 나에 관한 것이라 늘 맨 위. 월간 랭킹은 남과 견주는 것이라 접어 둘 수 있고, 접힌 상태는
 * 이 기기에만 기억한다(localStorage). 새 달이 시작된 뒤 처음 팀 화면을 열면 팀 페이지가 이 탭을 먼저 보여 주고
 * 지난달 최종 순위를 펼쳐 준다(`newMonth`). 배지는 얻기만 하고 자랑하는 기능은 없다 — 다음 할 일을 알려 주는 용도.
 *
 * 코트 마진은 실력 지표가 아니라 "그 달 코트에서 벌어진 결과" 다 (설계서 9.1절). 문구도 그렇게만 쓴다.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { peerApi } from '../api/peer'
import { teamsApi } from '../api/teams'
import { localISODate, type BadgeGroup, type BadgeView, type MarginPoint, type MonthlyMarginEntry } from '../api/types'
import { Avatar, Card, EmptyState, SectionTitle, Spinner } from './ui'

/** "2026-09" → "9월" (같은 해) / "2025년 12월" (다른 해) */
function monthLabel(p: string, today = localISODate()) {
  return p.slice(0, 4) === today.slice(0, 4) ? `${Number(p.slice(5))}월` : `${p.slice(0, 4)}년 ${Number(p.slice(5))}월`
}
/** "2026-09" 의 한 달 전 */
function prevMonth(p: string) {
  const y = Number(p.slice(0, 4)), m = Number(p.slice(5))
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, '0')}`
}
const fmtSigned = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`
const mmdd = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`

export function RecordsTab({ teamId, myPlayerId, newMonth }: { teamId: number; myPlayerId: number | null; newMonth: boolean }) {
  return (
    <div className="space-y-5">
      <TrendSection playerId={myPlayerId} />
      <MonthlyMarginSection teamId={teamId} newMonth={newMonth} />
      <BadgeSection />
    </div>
  )
}

/* ---------- 내 추세 ---------- */

function TrendSection({ playerId }: { playerId: number | null }) {
  const q = useQuery({ queryKey: ['stats', playerId], queryFn: () => peerApi.stats(playerId!), enabled: playerId !== null })
  const s = q.data
  return (
    <section>
      <SectionTitle action={s && s.quarters_played > 0 ? <span className="text-xs text-muted">참석 {s.events_attended}회 · 출전 {s.quarters_played}쿼터</span> : undefined}>내 추세</SectionTitle>
      {playerId === null ? <EmptyState title="팀원만 볼 수 있어요" /> : q.isLoading || !s ? <Spinner /> : s.quarters_played === 0 ? (
        <EmptyState title="아직 경기 기록이 없어요" desc={`참석 ${s.events_attended}회 · 매니저가 쿼터를 기록하면 활동일마다 점이 찍혀요.`} />
      ) : (
        <TrendChart points={s.margin_trend} />
      )}
    </section>
  )
}

/** 활동일별 평균 점수 차 꺾은선. 점 하나 = 일정 하나(그날 뛴 쿼터의 평균). 점을 누르면 그날 요약이 아래에 보인다 */
export function TrendChart({ points }: { points: MarginPoint[] }) {
  const [sel, setSel] = useState<number | null>(null)
  const W = 320, H = 140, PX = 14, PT = 12, PB = 26
  const max = Math.max(3, ...points.map((m) => Math.abs(Number(m.avg_normalized_margin))))
  const x = (i: number) => (points.length === 1 ? W / 2 : PX + (i * (W - PX * 2)) / (points.length - 1))
  const y = (v: number) => PT + ((max - v) / (2 * max)) * (H - PT - PB)
  const path = points.map((m, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(Number(m.avg_normalized_margin)).toFixed(1)}`).join(' ')
  const cur = sel === null ? points[points.length - 1] : points[sel]
  const curIdx = sel === null ? points.length - 1 : sel
  // 날짜 라벨은 6개까지만. 마지막 점은 항상 표시하고, 그와 너무 가까운 라벨은 뺀다 (겹치지 않게)
  const step = Math.max(1, Math.ceil(points.length / 6))
  const last = points.length - 1
  const labelled = (i: number) => i === last || (i % step === 0 && last - i >= Math.max(1, Math.ceil(step / 2)))
  const wins = points.reduce((a, m) => a + m.wins, 0), games = points.reduce((a, m) => a + m.wins + m.losses, 0)
  return (
    <Card className="space-y-2">
      <p className="text-[11px] text-faint">활동일마다 뛴 쿼터의 평균 점수 차예요. 팀 결과라서 개인 실력 그 자체는 아니에요. 점을 누르면 그날 요약이 보여요.</p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="활동일별 평균 점수 차">
        <line x1={PX} x2={W - PX} y1={y(0)} y2={y(0)} stroke="var(--color-line-strong)" strokeDasharray="3 3" />
        <text x={W - PX} y={y(max) + 4} fontSize="9" fill="var(--color-faint)" textAnchor="end">+{max.toFixed(0)}</text>
        <text x={W - PX} y={y(-max) + 4} fontSize="9" fill="var(--color-faint)" textAnchor="end">−{max.toFixed(0)}</text>
        {points.length > 1 && <path d={path} fill="none" stroke="var(--color-navy-300)" strokeWidth="2" strokeLinejoin="round" />}
        {points.map((m, i) => {
          const v = Number(m.avg_normalized_margin)
          const r = 3 + Math.min(3, m.quarters / 3)
          return (
            <g key={m.event_id} onClick={() => setSel(i)} className="cursor-pointer">
              <circle cx={x(i)} cy={y(v)} r={r + 6} fill="transparent" />
              <circle cx={x(i)} cy={y(v)} r={r} fill={v > 0 ? 'var(--color-court-500)' : v < 0 ? '#f43f5e' : 'var(--color-faint)'} stroke={i === curIdx ? 'var(--color-ink)' : 'white'} strokeWidth={i === curIdx ? 2 : 1.5} />
              {labelled(i) && (
                <text x={x(i)} y={H - 8} fontSize="9" fill="var(--color-muted)" textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'}>{mmdd(m.event_date)}</text>
              )}
            </g>
          )
        })}
      </svg>
      <div className="flex items-center justify-between rounded-xl bg-surface-2 px-3 py-2 text-xs">
        <span className="text-muted">{mmdd(cur.event_date)}{cur.title ? ` · ${cur.title}` : ''}</span>
        <span className="font-semibold text-ink">
          <span className={Number(cur.avg_normalized_margin) > 0 ? 'text-ok-ink' : Number(cur.avg_normalized_margin) < 0 ? 'text-danger-ink' : 'text-muted'}>평균 {fmtSigned(Number(cur.avg_normalized_margin))}</span>
          <span className="text-faint"> · {cur.wins}승 {cur.losses}패 · {cur.quarters}쿼터</span>
        </span>
      </div>
      <p className="text-[11px] text-muted">전체 {points.length}일 · 이긴 쿼터 {wins}/{games}</p>
    </Card>
  )
}

/* ---------- 월간 코트 마진 ---------- */

const collapsedKey = (teamId: number) => `hooply:margin-rank-collapsed:${teamId}`

function MonthlyMarginSection({ teamId, newMonth }: { teamId: number; newMonth: boolean }) {
  const nav = useNavigate()
  const today = localISODate()
  const thisMonth = today.slice(0, 7)
  const periods = useQuery({ queryKey: ['events', 'team', teamId, 'periods'], queryFn: () => teamsApi.leaderboardPeriods(teamId) })
  const months = periods.data?.items ?? []
  // 새 달의 첫 방문이면 지난달 최종 순위를, 아니면 이번 달(기록이 없으면 기록 있는 가장 최근 달)을 먼저 보여 준다
  const initial = newMonth && months.includes(prevMonth(thisMonth)) ? prevMonth(thisMonth) : months.includes(thisMonth) ? thisMonth : (months[0] ?? thisMonth)
  const [chosen, setChosen] = useState<string | null>(null)
  const period = chosen ?? initial
  // 접힘은 이 기기에만 기억한다. 새 달 첫 방문에는 접혀 있어도 펼쳐 보여 준다
  const [collapsed, setCollapsed] = useState<boolean>(() => { try { return !newMonth && localStorage.getItem(collapsedKey(teamId)) === '1' } catch { return false } })
  const toggle = () => { const next = !collapsed; setCollapsed(next); try { localStorage.setItem(collapsedKey(teamId), next ? '1' : '0') } catch { /* ignore */ } }
  const q = useQuery({ queryKey: ['team', teamId, 'monthly-margin', period], queryFn: () => teamsApi.monthlyMargin(teamId, period), enabled: !periods.isLoading })
  const v = q.data
  const top = v?.items.find((e) => e.rank === 1)
  const options = months.includes(thisMonth) ? months : [thisMonth, ...months]

  return (
    <section>
      <SectionTitle action={<button onClick={toggle} aria-expanded={!collapsed} className="min-h-8 rounded-lg px-2 text-xs font-semibold text-ink-2">{collapsed ? '펼치기 ▾' : '접기 ▴'}</button>}>월간 코트 마진</SectionTitle>
      <Card className="space-y-2 p-0">
        {!collapsed && (
          <div className="flex items-center gap-2 px-4 pt-3">
            <label htmlFor="margin-period" className="text-xs font-semibold text-muted">달</label>
            <select
              id="margin-period" value={period} onChange={(e) => setChosen(e.target.value)} disabled={periods.isLoading}
              className="min-h-9 flex-1 rounded-xl border border-line bg-surface px-3 text-sm font-semibold text-ink"
            >
              {options.map((p) => <option key={p} value={p}>{monthLabel(p, today)}{p === thisMonth ? ' (이번 달)' : ''}</option>)}
            </select>
          </div>
        )}
        {!collapsed && newMonth && period !== thisMonth && (
          <p className="mx-4 rounded-xl bg-brand-soft px-3 py-2 text-xs font-semibold text-brand-ink">새 달이 시작됐어요. {monthLabel(period, today)} 최종 순위예요 — 이번 달 랭킹은 첫 기록부터 다시 쌓여요.</p>
        )}
        {collapsed ? (
          <button onClick={toggle} className="flex w-full items-center justify-between px-4 py-3 text-left text-sm">
            <span className="text-muted">{v ? (top ? <>{monthLabel(period, today)} 1위 <b className="text-ink">{top.player.display_name}</b> <span className="text-ok-ink">{fmtSigned(Number(top.avg_margin))}</span></> : `${monthLabel(period, today)} · 아직 순위가 없어요`) : '…'}</span>
            <span className="text-xs font-semibold text-ink-2">펼치기 ▾</span>
          </button>
        ) : q.isLoading || !v ? <div className="pb-3"><Spinner /></div> : (
          <>
            <p className="px-4 text-[11px] text-faint">
              {v.total_quarters === 0
                ? '이 달엔 아직 기록된 쿼터가 없어요.'
                : `출전 쿼터의 평균 점수 차 순서예요. 이 달 팀 전체 ${v.total_quarters}쿼터 중 ${v.threshold_quarters}쿼터(${Math.round(v.min_share * 100)}%) 이상 뛴 사람만 순위에 올라요. 실력이 아니라 이 달의 결과예요.`}
            </p>
            {v.items.length > 0 && (
              <div className="divide-y divide-line border-t border-line">
                {v.items.filter((e) => e.eligible).map((e) => <MarginRow key={e.player.id} e={e} />)}
                {v.items.some((e) => !e.eligible) && (
                  <>
                    <p className="bg-surface-2 px-4 py-1.5 text-[11px] font-semibold text-muted">집계 제외 · 출전 {v.threshold_quarters}쿼터 미만</p>
                    {v.items.filter((e) => !e.eligible).map((e) => <MarginRow key={e.player.id} e={e} dim />)}
                  </>
                )}
              </div>
            )}
            <button onClick={() => nav(`/teams/${teamId}/leaderboard`)} className="flex w-full items-center justify-between border-t border-line px-4 py-3 text-left text-sm font-semibold text-ink">
              <span>리더보드 더 보기 <span className="ml-1 text-[11px] font-normal text-muted">참여율 · 출전 쿼터</span></span><span>→</span>
            </button>
          </>
        )}
      </Card>
    </section>
  )
}

function MarginRow({ e, dim = false }: { e: MonthlyMarginEntry; dim?: boolean }) {
  const v = Number(e.avg_margin)
  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 ${dim ? 'opacity-60' : ''}`}>
      <span className={`w-6 text-center text-sm font-black ${e.rank !== null && e.rank <= 3 ? 'text-brand-ink' : 'text-faint'}`}>{e.rank ?? '–'}</span>
      <Avatar name={e.player.display_name} src={e.player.profile_image_url} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-ink">{e.player.display_name}</p>
        <p className="text-[11px] text-muted">출전 {e.quarters}쿼터 · {e.wins}승 {e.quarters - e.wins}패 · 합계 {fmtSigned(Number(e.total_margin))}</p>
      </div>
      <span className={`text-sm font-bold ${v > 0 ? 'text-ok-ink' : v < 0 ? 'text-danger-ink' : 'text-muted'}`}>{fmtSigned(v)}</span>
    </div>
  )
}

/* ---------- 배지 ---------- */

const GROUP_LABEL: Record<BadgeGroup, string> = { START: '시작', ACTIVITY: '활동', RELATION: '관계' }
const GROUP_ORDER: BadgeGroup[] = ['START', 'ACTIVITY', 'RELATION']

function BadgeSection() {
  const q = useQuery({ queryKey: ['me', 'badges'], queryFn: peerApi.myBadges })
  const items = q.data?.items ?? []
  const earned = items.filter((b) => b.earned_at).length
  return (
    <section>
      <SectionTitle action={items.length ? <span className="text-xs text-muted">획득 {earned}/{items.length}</span> : undefined}>배지</SectionTitle>
      {q.isLoading ? <Spinner /> : (
        <Card className="space-y-3">
          <p className="text-[11px] text-faint">실력이 아니라 함께한 행동으로 얻어요. 회색은 아직 못 얻은 배지고, 숫자는 진행 정도예요.</p>
          {GROUP_ORDER.map((g) => (
            <div key={g}>
              <p className="mb-1.5 text-xs font-bold text-muted">{GROUP_LABEL[g]}</p>
              <div className="grid grid-cols-3 gap-2">
                {items.filter((b) => b.group === g).map((b) => <BadgeTile key={b.code} b={b} />)}
              </div>
            </div>
          ))}
        </Card>
      )}
    </section>
  )
}

function BadgeTile({ b }: { b: BadgeView }) {
  const done = !!b.earned_at
  return (
    <div title={b.description} className={`flex min-h-[76px] flex-col items-center justify-center rounded-xl px-1.5 py-2 text-center ${done ? 'border border-brand-line bg-brand-soft' : 'bg-sunken'}`}>
      <span className={`mb-1 h-2 w-2 rounded-full ${done ? 'bg-court-500' : 'bg-line-strong'}`} />
      <p className={`text-[11px] font-semibold leading-tight ${done ? 'text-ink' : 'text-faint'}`}>{b.title}</p>
      <p className="mt-0.5 text-[10px] text-faint">{done ? mmdd(b.earned_at!.slice(0, 10)) : b.threshold > 1 ? `${b.progress}/${b.threshold}` : '아직'}</p>
    </div>
  )
}
