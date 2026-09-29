/**
 * 팀 화면 "전술" 탭 (S-28, docs/07 FR-45 · FR-46).
 *
 * 위: 다가오는 확정 배정이 있으면 그날 전술. 매니저에게는 팀별 추천(적합도·자리별 선수), 참석자에게는 매니저가 이름표를
 *     저장한 전술만. 추천의 점수와 속성은 설문에서 나온 개인 특성이라 매니저에게만 보인다.
 * 아래: 전체 프리셋 목록. 누르면 전술판으로.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { eventsApi } from '../api/events'
import { tacticsApi } from '../api/tactics'
import { localISODate, type EventView, type PlayRecommendation, type SquadRecommendation } from '../api/types'
import { DEFENSE_LABEL, ROLE_LABEL } from '../lib/tactics'
import { Badge, Card, EmptyState, SectionTitle, Spinner } from './ui'

const CIRCLED = ['①', '②', '③', '④', '⑤']
const mmdd = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
const keyOf = (playKey: string) => playKey.replace(/^preset:/, '')

/** 오늘 이후 가장 가까운, 배정이 확정된 일정 */
function useUpcomingAdopted(teamId: number) {
  const events = useQuery({ queryKey: ['events', 'team', teamId, 'all', 50], queryFn: () => eventsApi.list(teamId, { size: 50 }) })
  const today = localISODate()
  const ev = (events.data?.items ?? [])
    .filter((e) => e.adopted_candidate_id && e.status !== 'CANCELED' && e.event_date >= today)
    .sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))[0]
  return { event: ev ?? null, loading: events.isLoading }
}

export function TacticsTab({ teamId, isManager }: { teamId: number; isManager: boolean }) {
  const nav = useNavigate()
  const { event, loading } = useUpcomingAdopted(teamId)
  const presets = useQuery({ queryKey: ['tactics', 'presets'], queryFn: tacticsApi.presets, staleTime: Infinity })
  const saved = useQuery({
    queryKey: ['tactics', 'saved', event?.id], queryFn: () => tacticsApi.saved(event!.id), enabled: !!event && !isManager, retry: false,
  })
  // 일정 이름표까지 보여 줄 수 있으면 전술판에 일정을 넘긴다 (참석하지 않은 팀원은 전술만)
  const eventParam = event && (isManager || saved.isSuccess) ? `?event=${event.id}` : ''

  return (
    <div className="space-y-5">
      {loading ? <Spinner /> : event && (
        isManager ? <RecommendSection event={event} /> : saved.isSuccess && (
          <section>
            <SectionTitle>{mmdd(event.event_date)} 우리 팀 전술</SectionTitle>
            {saved.data.items.length ? (
              <div className="space-y-2">
                {saved.data.items.map((s) => (
                  <Card key={`${s.play_key}-${s.squad_no}`} onClick={() => nav(`/tactics/${keyOf(s.play_key)}?event=${event.id}&squad=${s.squad_no}`)} className="flex items-center gap-3 py-3">
                    <SquadChip no={s.squad_no} name={s.squad_name} />
                    <span className="flex-1 font-semibold text-ink">{s.name}</span>
                    {saved.data.my_squad_no === s.squad_no && <Badge tone="court">내 팀</Badge>}
                    <span className="text-faint" aria-hidden="true">›</span>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState title="아직 정해진 전술이 없어요" desc="매니저가 전술판에서 자리를 정하면 여기에 보여요." />
            )}
          </section>
        )
      )}

      <section>
        <SectionTitle>전술 목록</SectionTitle>
        {presets.isLoading ? <Spinner /> : (
          <div className="space-y-2">
            {presets.data?.items.map((p) => (
              <Card key={p.key} onClick={() => nav(`/tactics/${p.key}${eventParam}`)} className="space-y-1 py-3" label={`${p.name} 전술판 보기`}>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-ink">{p.name}</span>
                  <Badge tone={p.defense === 'zone' ? 'navy' : 'neutral'}>{DEFENSE_LABEL[p.defense]}</Badge>
                  <span className="ml-auto text-faint" aria-hidden="true">›</span>
                </div>
                <p className="text-xs text-muted">{p.summary}</p>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SquadChip({ no, name }: { no: number; name: string }) {
  return (
    <span className={`inline-flex min-w-12 justify-center rounded-full px-2 py-0.5 text-xs font-bold ${no === 1 ? 'bg-team-black text-team-black-ink' : 'border border-line-strong bg-team-white text-team-white-ink'}`}>
      {name}
    </span>
  )
}

/* ---------- 매니저: 팀별 추천 ---------- */

function RecommendSection({ event }: { event: EventView }) {
  const [zone, setZone] = useState(false)
  const rec = useQuery({ queryKey: ['tactics', 'recommend', event.id, zone], queryFn: () => tacticsApi.recommend(event.id, zone) })
  return (
    <section className="space-y-3">
      <SectionTitle>{mmdd(event.event_date)} 팀에 맞는 전술</SectionTitle>
      <label className="flex min-h-11 items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4">
        <span className="text-sm text-ink">상대가 지역 수비를 써요<span className="block text-[11px] text-muted">켜면 지역 수비 공략 전술만 추천해요</span></span>
        <input type="checkbox" role="switch" checked={zone} onChange={(e) => setZone(e.target.checked)} className="size-5 accent-[var(--color-brand)]" />
      </label>
      <p className="text-[11px] text-faint">설문·키·포지션으로 자리마다 잘 맞는 사람을 골랐어요. 점수는 매니저에게만 보여요.</p>
      {rec.isLoading ? <Spinner /> : rec.isError ? <EmptyState title="추천을 불러오지 못했어요" /> : rec.data?.squads.map((sq) => (
        <SquadRecommend key={sq.squad_no} sq={sq} eventId={event.id} />
      ))}
    </section>
  )
}

function SquadRecommend({ sq, eventId }: { sq: SquadRecommendation; eventId: number }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2"><SquadChip no={sq.squad_no} name={sq.squad_name} /><span className="text-xs text-muted">{sq.member_count}명</span></div>
      {sq.items.length === 0 ? (
        <p className="text-xs text-muted">5명 이상이어야 추천할 수 있어요.</p>
      ) : sq.items.map((it, i) => <RecommendCard key={it.play_key} it={it} rank={i + 1} squadNo={sq.squad_no} eventId={eventId} />)}
    </div>
  )
}

function RecommendCard({ it, rank, squadNo, eventId }: { it: PlayRecommendation; rank: number; squadNo: number; eventId: number }) {
  const nav = useNavigate()
  const [open, setOpen] = useState(rank === 1)
  const fill = it.slots.map((s) => s.player_id).join(',')
  return (
    <Card className="space-y-2 py-3">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left" aria-expanded={open}>
        <span className="text-xs font-bold text-muted">{rank}</span>
        <span className="flex-1 font-semibold text-ink">{it.name}</span>
        <span className="text-sm font-bold text-brand-ink">적합도 {Math.round(it.fit)}</span>
        <span className="text-faint" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <>
          <ul className="space-y-1.5">
            {it.slots.map((s) => (
              <li key={s.slot} className="text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-brand-ink">{CIRCLED[s.slot - 1]}</span>
                  <span className="w-24 text-ink-2">{ROLE_LABEL[s.role]}</span>
                  <span className="flex-1 truncate font-semibold text-ink">{s.display_name}</span>
                  <span className="text-xs text-muted">{s.score}</span>
                </div>
                {(s.matched_attrs.length > 0 || s.missing_attrs.length > 0 || s.alt_display_name) && (
                  <p className="ml-8 text-[11px] leading-relaxed text-muted">
                    {s.matched_attrs.length > 0 && <span>{s.matched_attrs.slice(0, 3).join(' · ')}</span>}
                    {s.missing_attrs.length > 0 && <span className="text-warn-ink">{s.matched_attrs.length ? ' · ' : ''}부족: {s.missing_attrs.join(' · ')}</span>}
                    {s.alt_display_name && <span className="text-faint"> · 교체 후보 {s.alt_display_name}</span>}
                  </p>
                )}
              </li>
            ))}
          </ul>
          <button
            type="button" onClick={() => nav(`/tactics/${keyOf(it.play_key)}?event=${eventId}&squad=${squadNo}&fill=${fill}`)}
            className="min-h-11 w-full rounded-xl border border-brand-line bg-brand-soft text-sm font-semibold text-brand-ink active:opacity-80"
          >
            전술판에서 보고 이름표 저장
          </button>
        </>
      )}
    </Card>
  )
}
