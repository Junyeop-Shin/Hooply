/**
 * 팀 화면 "전술" 탭 (S-28, docs/07 FR-45 · FR-46) 과 배정 결과 화면의 추천 전술 카드.
 *
 * 위: 다가오는 **확정 배정**이 있으면 그날 추천 전술이 자동으로 뜬다 — 매니저가 고르지 않는다. 팀마다 적합도 기준
 *     (서버 `fit_min`)을 넘은 전술 중 상위 3개. 그날 참석자는 누구나 본다. 자리마다 가장 잘 맞는 사람과 괄호 안에
 *     예비(같은 전술판 5명 중 그 역할도 맞는 사람)를 보여 준다. 자리별 점수·속성은 설문에서 나온 개인 특성이라 매니저에게만.
 *     팀마다 "AI 코치" 한 줄과, 카드 안에 AI 가 쓴 이유 · 핵심 자리 · 주의할 점 (체인 C, docs/07 FR-52). 실패하면 규칙 정보만.
 * 아래: 전체 전술 목록. 누르면 전술판으로.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { eventsApi } from '../api/events'
import { tacticsApi } from '../api/tactics'
import { localISODate, type AiTacticItem, type EventView, type Play, type PlayLineup, type SlotLineup, type SquadRecommendation } from '../api/types'
import { DEFENSE_LABEL, ROLE_LABEL } from '../lib/tactics'
import { Thinking, TypedSections } from './ai-cards'
import { FirstTimeTip } from './tutorial'
import { Badge, Card, EmptyState, SectionTitle, Spinner } from './ui'

export const CIRCLED = ['①', '②', '③', '④', '⑤']
const mmdd = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
const keyOf = (playKey: string) => playKey.replace(/^preset:/, '')
export const boardPath = (playKey: string, eventId: number, squadNo: number) => `/tactics/${keyOf(playKey)}?event=${eventId}&squad=${squadNo}`

/** 오늘 이후 가장 가까운, 배정이 확정된 일정 */
function useUpcomingAdopted(teamId: number) {
  const events = useQuery({ queryKey: ['events', 'team', teamId, 'all', 50], queryFn: () => eventsApi.list(teamId, { size: 50 }) })
  const today = localISODate()
  const ev = (events.data?.items ?? [])
    .filter((e) => e.adopted_candidate_id && e.status !== 'CANCELED' && e.event_date >= today)
    .sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))[0]
  return { event: ev ?? null, loading: events.isLoading }
}

/** AI 전술 추천 설명 (체인 C) — 한 팀. 추천이 있을 때만 부른다 */
export function useAiTactics(eventId: number, squadNo: number, zone: boolean, enabled: boolean) {
  return useQuery({
    queryKey: ['ai', 'tactics', eventId, squadNo, zone],
    queryFn: () => tacticsApi.aiRecommend(eventId, squadNo, zone),
    enabled, staleTime: Infinity, retry: false,
  })
}

/** 그날 추천. 참석하지 않은 팀원은 403 — 조용히 숨긴다 */
export function useRecommendation(eventId: number | null, zone: boolean) {
  return useQuery({
    queryKey: ['tactics', 'recommend', eventId, zone],
    queryFn: () => tacticsApi.recommend(eventId!, zone),
    enabled: eventId !== null,
    retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 2,
  })
}

export function TacticsTab({ teamId }: { teamId: number }) {
  const nav = useNavigate()
  const { event, loading } = useUpcomingAdopted(teamId)
  const presets = useQuery({ queryKey: ['tactics', 'presets'], queryFn: tacticsApi.presets, staleTime: Infinity })
  const [zone, setZone] = useState(false)
  const rec = useRecommendation(event?.id ?? null, zone)
  // 그날 참석자면 목록에서 들어가도 전술판에 그날 자리 배치를 함께 보여 준다
  const eventParam = event && rec.isSuccess ? `?event=${event.id}` : ''

  return (
    <div className="space-y-5">
      <FirstTimeTip id="tactics" />
      {loading ? <Spinner /> : event && !(rec.error instanceof ApiError && rec.error.status === 403) && (
        <EventRecommend event={event} zone={zone} setZone={setZone} rec={rec} />
      )}

      <PresetGroup title="전술 목록" items={presets.data?.items.filter((p) => p.situation === 'half_court')} loading={presets.isLoading} onOpen={(k) => nav(`/tactics/${k}${eventParam}`)} />
      <PresetGroup
        title="인바운드" desc="골밑 베이스라인에서 공을 넣을 때 쓰는 전술이에요. 오늘 추천에는 들어가지 않아요."
        items={presets.data?.items.filter((p) => p.situation === 'inbound')} loading={presets.isLoading} onOpen={(k) => nav(`/tactics/${k}${eventParam}`)}
      />
    </div>
  )
}

function PresetGroup({ title, desc, items, loading, onOpen }: { title: string; desc?: string; items?: Play[]; loading: boolean; onOpen: (key: string) => void }) {
  if (!loading && !items?.length) return null
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      {desc && <p className="-mt-1 mb-2 px-1 text-[11px] text-muted">{desc}</p>}
      {loading ? <Spinner /> : (
        <div className="space-y-2">
          {items?.map((p) => (
            <Card key={p.key} onClick={() => onOpen(p.key)} className="space-y-1 py-3" label={`${p.name} 전술판 보기`}>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-ink">{p.name}</span>
                {p.situation === 'half_court' && <Badge tone={p.defense === 'zone' ? 'navy' : 'neutral'}>{DEFENSE_LABEL[p.defense]}</Badge>}
                <span className="ml-auto text-faint" aria-hidden="true">›</span>
              </div>
              <p className="text-xs text-muted">{p.summary}</p>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}

function SquadChip({ no, name }: { no: number; name: string }) {
  return (
    <span className={`inline-flex min-w-12 justify-center rounded-full px-2 py-0.5 text-xs font-bold ${no === 1 ? 'bg-team-black text-team-black-ink' : 'border border-line-strong bg-team-white text-team-white-ink'}`}>
      {name}
    </span>
  )
}

function EventRecommend({ event, zone, setZone, rec }: {
  event: EventView; zone: boolean; setZone: (z: boolean) => void; rec: ReturnType<typeof useRecommendation>
}) {
  const data = rec.data
  // 내 팀을 먼저
  const squads = data ? [...data.squads].sort((a, b) => Number(b.squad_no === data.my_squad_no) - Number(a.squad_no === data.my_squad_no)) : []
  return (
    <section className="space-y-3">
      <SectionTitle>{mmdd(event.event_date)} 추천 전술</SectionTitle>
      <label className="flex min-h-11 items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4">
        <span className="text-sm text-ink">상대가 지역 수비를 써요<span className="block text-[11px] text-muted">켜면 지역 수비 공략 전술만 보여 줘요</span></span>
        <input type="checkbox" role="switch" checked={zone} onChange={(e) => setZone(e.target.checked)} className="size-5 accent-[var(--color-brand)]" />
      </label>
      {rec.isLoading ? <Spinner /> : !data ? <EmptyState title="추천을 불러오지 못했어요" /> : (
        <>
          <p className="text-[11px] text-faint">
            확정된 팀 구성으로 자리마다 가장 잘 맞는 사람을 골랐어요. 적합도 {data.fit_min} 이상인 전술만 추천해요.
            괄호 안은 같은 전술판에서 그 역할도 할 수 있는 예비예요.
          </p>
          {squads.map((sq) => <SquadRecommend key={sq.squad_no} sq={sq} eventId={event.id} zone={zone} mine={sq.squad_no === data.my_squad_no} fitMin={data.fit_min} manager={data.can_edit} />)}
        </>
      )}
    </section>
  )
}

function SquadRecommend({ sq, eventId, zone, mine, fitMin, manager }: { sq: SquadRecommendation; eventId: number; zone: boolean; mine: boolean; fitMin: number; manager: boolean }) {
  const ai = useAiTactics(eventId, sq.squad_no, zone, sq.items.length > 0)
  const aiOk = ai.data && !ai.data.fallback ? ai.data : null
  const aiOf = (key: string) => aiOk?.items.find((x) => x.play_key === key)
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <SquadChip no={sq.squad_no} name={sq.squad_name} />
        <span className="text-xs text-muted">{sq.member_count}명</span>
        {mine && <Badge tone="court">내 팀</Badge>}
      </div>
      {sq.member_count < 5 ? (
        <p className="text-xs text-muted">5명 이상이어야 추천할 수 있어요.</p>
      ) : sq.items.length === 0 ? (
        <p className="rounded-xl bg-surface-2 px-3 py-2.5 text-xs text-muted">오늘 팀 구성으로는 적합도 {fitMin}를 넘는 전술이 없어요. 아래 목록에서 직접 골라 볼 수 있어요.</p>
      ) : (
        <>
          {ai.isLoading ? (
            <div className="rounded-xl bg-brand-soft px-3 py-2"><Thinking label="AI 코치가 전술을 읽고 있어요…" /></div>
          ) : aiOk?.one_liner && (
            <div className="rounded-xl bg-brand-soft px-3 py-2">
              <p className="mb-0.5 text-[10px] font-black text-brand-ink">AI 코치</p>
              <TypedSections note={false} sections={[{ items: [aiOk.one_liner], tone: 'lead' }]} />
            </div>
          )}
          {sq.items.map((it, i) => (
            <LineupCard key={it.play_key} it={it} rank={i + 1} open={i === 0} to={boardPath(it.play_key, eventId, sq.squad_no)} manager={manager} ai={aiOf(it.play_key)} />
          ))}
        </>
      )}
    </div>
  )
}

/** "허재 (예비: 양동근 · 김승현)" */
export function SlotPeople({ s }: { s: SlotLineup }) {
  return (
    <>
      <span className="font-semibold text-ink">{s.display_name}</span>
      {s.backups.length > 0 && <span className="text-muted"> (예비: {s.backups.map((b) => b.display_name).join(' · ')})</span>}
    </>
  )
}

function LineupCard({ it, rank, open: initial, to, manager, ai }: { it: PlayLineup; rank: number; open: boolean; to: string; manager: boolean; ai?: AiTacticItem }) {
  const nav = useNavigate()
  const [open, setOpen] = useState(initial)
  return (
    <Card className="space-y-2 py-3">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left" aria-expanded={open}>
        <span className="text-xs font-bold text-muted">{rank}</span>
        <span className="flex-1 font-semibold text-ink">{it.name}</span>
        {it.manual && <Badge tone="navy">매니저 배치</Badge>}
        <span className="text-sm font-bold text-brand-ink">적합도 {Math.round(it.fit)}</span>
        <span className="text-faint" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <>
          {ai && (
            <div className="rounded-xl border border-brand-line px-3 py-2">
              <TypedSections sections={[
                { items: [ai.reason], tone: 'lead' },
                { title: '핵심 자리', items: ai.key_roles },
                { title: '주의할 점', items: ai.caution ? [ai.caution] : [], tone: 'warn' },
              ]} />
            </div>
          )}
          <ul className="space-y-1.5">
            {it.slots.map((s) => (
              <li key={s.slot} className="text-sm">
                <div className="flex gap-2">
                  <span className="font-bold text-brand-ink">{CIRCLED[s.slot - 1]}</span>
                  <span className="w-24 shrink-0 text-ink-2">{ROLE_LABEL[s.role]}</span>
                  <span className="min-w-0 flex-1"><SlotPeople s={s} /></span>
                  {manager && s.score !== null && <span className="text-xs text-muted">{s.score}</span>}
                </div>
                {manager && (s.matched_attrs.length > 0 || s.missing_attrs.length > 0 || s.alt_display_name) && (
                  <p className="ml-8 text-[11px] leading-relaxed text-muted">
                    {s.matched_attrs.length > 0 && <span>{s.matched_attrs.slice(0, 3).join(' · ')}</span>}
                    {s.missing_attrs.length > 0 && <span className="text-warn-ink">{s.matched_attrs.length ? ' · ' : ''}부족: {s.missing_attrs.join(' · ')}</span>}
                    {s.alt_display_name && <span className="text-faint"> · 벤치 교체 후보 {s.alt_display_name}</span>}
                  </p>
                )}
              </li>
            ))}
          </ul>
          <button
            type="button" onClick={() => nav(to)}
            className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-soft text-sm font-semibold text-brand-ink active:opacity-80"
          >
            전술판에서 보기{manager ? ' · 자리 바꾸기' : ''}
          </button>
        </>
      )}
    </Card>
  )
}

/** 배정 결과 화면(S-14)의 "오늘 추천 전술" — 내 팀(없으면 두 팀) 추천 이름만 짧게, 누르면 전술판 */
export function AdoptedTactics({ eventId }: { eventId: number }) {
  const nav = useNavigate()
  const rec = useRecommendation(eventId, false)
  if (!rec.data) return null
  const d = rec.data
  const squads = d.squads.filter((s) => d.my_squad_no === null || s.squad_no === d.my_squad_no)
  if (!squads.some((s) => s.items.length)) return null
  return (
    <section>
      <SectionTitle>오늘 추천 전술</SectionTitle>
      {d.my_squad_no !== null && <AiOneLiner eventId={eventId} squadNo={d.my_squad_no} />}
      <Card className="divide-y divide-line p-0">
        {squads.flatMap((sq) => sq.items.map((it) => (
          <button key={`${sq.squad_no}-${it.play_key}`} type="button" onClick={() => nav(boardPath(it.play_key, eventId, sq.squad_no))} className="flex min-h-12 w-full items-center gap-2 px-4 text-left active:bg-sunken">
            <SquadChip no={sq.squad_no} name={sq.squad_name} />
            <span className="flex-1 font-semibold text-ink">{it.name}</span>
            <span className="text-xs font-bold text-brand-ink">적합도 {Math.round(it.fit)}</span>
            <span className="text-faint" aria-hidden="true">›</span>
          </button>
        )))}
      </Card>
      <p className="mt-1.5 text-[11px] text-faint">팀 화면 전술 탭에서 자리와 예비까지 볼 수 있어요.</p>
    </section>
  )
}

function AiOneLiner({ eventId, squadNo }: { eventId: number; squadNo: number }) {
  const ai = useAiTactics(eventId, squadNo, false, true)
  if (!ai.data || ai.data.fallback || !ai.data.one_liner) return null
  return (
    <div className="mb-2 rounded-xl bg-brand-soft px-3 py-2">
      <p className="mb-0.5 text-[10px] font-black text-brand-ink">AI 코치</p>
      <TypedSections note={false} sections={[{ items: [ai.data.one_liner], tone: 'lead' }]} />
    </div>
  )
}
