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
import { localISODate, type BadgeGroup, type BadgeTier, type BadgeView, type MarginPoint, type MonthlyMarginEntry } from '../api/types'
import { SERIES_INFO, SINGLE_PICT, type BadgeFrame, type BadgePict } from './badge-art'
import { BadgeDefs, BadgeIcon } from './badge-icon'
import { FirstTimeTip } from './tutorial'
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
      <FirstTimeTip id="records" />
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
// 같은 행동을 쌓는 배지(묶음)는 칸 하나로 합쳐 동 → 은 → 금으로 올라가고, 한 번이면 끝나는 배지는 단일 칸.
// 칸을 누르면 아래에서 시트가 올라와 단계별로 얻은 날짜·남은 양을 보여 준다. 자랑·공유·획득 알림은 없다.

const GROUP_LABEL: Record<BadgeGroup, string> = { START: '시작', ACTIVITY: '활동', RELATION: '관계' }
const GROUP_ORDER: BadgeGroup[] = ['START', 'ACTIVITY', 'RELATION']
const TIER_KO: Record<BadgeTier, string> = { BRONZE: '동', SILVER: '은', GOLD: '금' }
const TIER_FRAME: Record<BadgeTier, BadgeFrame> = { BRONZE: 'bronze', SILVER: 'silver', GOLD: 'gold' }

/** 화면의 칸 하나 — 단일 배지 1개 또는 묶음(동·은·금 3개) */
interface BadgeTileModel { key: string; group: BadgeGroup; title: string; pict: BadgePict; desc: string; items: BadgeView[] }

function toTiles(items: BadgeView[]): BadgeTileModel[] {
  const tiles: BadgeTileModel[] = []
  const bySeries = new Map<string, BadgeTileModel>()
  for (const b of items) {
    if (b.series) {
      let t = bySeries.get(b.series)
      if (!t) {
        const info = SERIES_INFO[b.series] ?? { title: b.title, pict: 'ball' as BadgePict, desc: b.description }
        t = { key: b.series, group: b.group, title: info.title, pict: info.pict, desc: info.desc, items: [] }
        bySeries.set(b.series, t); tiles.push(t)
      }
      t.items.push(b)
    } else {
      tiles.push({ key: b.code, group: b.group, title: b.title, pict: SINGLE_PICT[b.code] ?? 'ball', desc: b.description, items: [b] })
    }
  }
  return tiles
}

/** 칸의 현재 모습: 틀, 칸 이름, 아래 줄 문구 */
function tileState(t: BadgeTileModel): { frame: BadgeFrame; title: string; sub: string; earned: boolean } {
  if (t.items.length === 1 && !t.items[0].series) {
    const b = t.items[0]
    if (b.earned_at) return { frame: 'single', title: t.title, sub: mmdd(b.earned_at.slice(0, 10)), earned: true }
    return { frame: 'locked', title: t.title, sub: b.threshold > 1 ? `${b.progress}/${b.threshold}` : '아직', earned: false }
  }
  const got = t.items.filter((b) => b.earned_at)
  const top = got[got.length - 1]
  const next = t.items.find((b) => !b.earned_at)
  if (!top) return { frame: 'locked', title: t.title, sub: `동까지 ${next!.progress}/${next!.threshold}`, earned: false }
  const tier = top.tier!
  return {
    frame: TIER_FRAME[tier], title: `${t.title} · ${TIER_KO[tier]}`, earned: true,
    sub: next ? `${TIER_KO[next.tier!]}까지 ${next.progress}/${next.threshold}` : `금 · ${mmdd(top.earned_at!.slice(0, 10))}`,
  }
}

function BadgeSection() {
  const q = useQuery({ queryKey: ['me', 'badges'], queryFn: peerApi.myBadges })
  const items = q.data?.items ?? []
  const tiles = toTiles(items)
  const earned = items.filter((b) => b.earned_at).length
  const [open, setOpen] = useState<BadgeTileModel | null>(null)
  return (
    <section>
      <BadgeDefs />
      <SectionTitle action={items.length ? <span className="text-xs text-muted">획득 {earned}/{items.length}</span> : undefined}>배지</SectionTitle>
      {q.isLoading ? <Spinner /> : (
        <Card className="space-y-3">
          <p className="text-[11px] text-faint">함께한 행동으로 얻어요. 칸을 누르면 단계와 남은 양이 보여요.</p>
          {GROUP_ORDER.map((g) => (
            <div key={g}>
              <p className="mb-1.5 text-xs font-bold text-muted">{GROUP_LABEL[g]}</p>
              <div className="grid grid-cols-4 gap-1.5">
                {tiles.filter((t) => t.group === g).map((t) => <BadgeTile key={t.key} t={t} onOpen={() => setOpen(t)} />)}
              </div>
            </div>
          ))}
        </Card>
      )}
      {open && <BadgeSheet t={open} onClose={() => setOpen(null)} />}
    </section>
  )
}

function BadgeTile({ t, onOpen }: { t: BadgeTileModel; onOpen: () => void }) {
  const st = tileState(t)
  return (
    <button
      type="button" onClick={onOpen} aria-label={`${st.title} 자세히 보기`}
      className={`flex min-h-[92px] flex-col items-center justify-start rounded-xl px-1 pb-2 pt-2.5 text-center active:opacity-80 ${st.earned ? 'border border-brand-line bg-brand-soft' : 'border border-transparent bg-sunken'}`}
    >
      <BadgeIcon frame={st.frame} pict={t.pict} label={st.title} className="mb-1 w-[38px]" />
      <span className={`text-[10.5px] font-semibold leading-tight ${st.earned ? 'text-ink' : 'text-faint'}`}>{st.title}</span>
      <span className="mt-0.5 text-[9.5px] tabular-nums text-faint">{st.sub}</span>
    </button>
  )
}

/** 칸을 누르면 올라오는 시트 — 게스트 초대 시트와 같은 모양 */
function BadgeSheet({ t, onClose }: { t: BadgeTileModel; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40" onClick={onClose} role="dialog" aria-modal="true" aria-label={`${t.title} 배지`}>
      <div className="safe-bottom max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-strong" />
        <div className="flex items-start justify-between">
          <h3 className="text-lg font-bold text-ink">{t.title}</h3>
          <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 flex size-9 items-center justify-center rounded-full text-xl text-faint active:bg-sunken">×</button>
        </div>
        <p className="mb-3 text-xs text-muted">{t.desc}</p>
        <div className="divide-y divide-line">
          {t.items.map((b) => {
            const done = !!b.earned_at
            const frame: BadgeFrame = done ? (b.tier ? TIER_FRAME[b.tier] : 'single') : 'locked'
            const pct = Math.min(100, Math.round((b.progress / b.threshold) * 100))
            return (
              <div key={b.code} className="flex items-center gap-3 py-2.5">
                <BadgeIcon frame={frame} pict={t.pict} label={b.title} className="w-12 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className={`text-sm font-semibold ${done ? 'text-ink' : 'text-muted'}`}>{b.tier ? `${TIER_KO[b.tier]} · ` : ''}{b.title}</p>
                  {done ? (
                    <p className="text-xs tabular-nums text-muted">{mmdd(b.earned_at!.slice(0, 10))} 달성</p>
                  ) : (
                    <>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full rounded-full bg-brand" style={{ width: `${pct}%` }} /></div>
                      <p className="mt-0.5 text-xs tabular-nums text-muted">{b.progress}/{b.threshold}</p>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
