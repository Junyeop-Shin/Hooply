/**
 * 팀 화면 "전술" 탭 (S-28) 과 확정된 일정 화면의 추천 전술 카드 (docs/07 FR-45 · FR-46).
 *
 * 전술 탭 (v1.7): 일정 추천은 없고 전술 목록만 — 맨 위 "별표 전술"(매니저가 별표, FR-61) → 우리 팀 전술(팀원 누구나
 *   "새 전술 만들기", FR-57) → 전술 목록 → 인바운드. 별표한 전술은 원래 묶음에서 빠지고 맨 위로 올라간다. 누르면 전술판으로.
 * 일정 화면 추천(EventTactics): 확정 배정이 있으면 팀마다 적합도 기준(서버 `fit_min`)을 넘은 전술 중 상위 3개를 자동으로
 *   보여 준다. 카드는 모두 접힌 채로 시작한다. 자리마다 가장 잘 맞는 사람과 예비, 자리별 점수·속성은 매니저에게만.
 *   팀마다 "AI 코치" 한 줄과, 카드 안에 AI 가 쓴 이유 · 핵심 자리 · 주의할 점 (체인 C, FR-52). 실패하면 규칙 정보만.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { tacticStarsApi, tacticsApi, teamPlaysApi } from '../api/tactics'
import type { AiTacticItem, EventView, Play, PlayLineup, SlotLineup, SquadRecommendation } from '../api/types'
import { DEFENSE_LABEL, ROLE_LABEL } from '../lib/tactics'
import { Thinking, TypedSections } from './ai-cards'
import { FirstTimeTip } from './tutorial'
import { squadStyle } from '../lib/squads'
import { Badge, EmptyState, SectionTitle, Spinner } from './ui'

export const CIRCLED = ['①', '②', '③', '④', '⑤']
const mmdd = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}`
/** play_key → 전술판 주소의 키 ("preset:high_pnr" → "high_pnr", "team:12" → "team_12") */
export const keyOf = (playKey: string) => playKey.replace(/^preset:/, '').replace(/^team:/, 'team_')
/** 전술판 주소의 키 → play_key */
const playKeyOf = (key: string) => (key.startsWith('team_') ? `team:${key.slice(5)}` : `preset:${key}`)
export const boardPath = (playKey: string, eventId: number, squadNo: number, zone = false) =>
  `/tactics/${keyOf(playKey)}?event=${eventId}&squad=${squadNo}${zone ? '&zone=1' : ''}`

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
  const qc = useQueryClient()
  const presets = useQuery({ queryKey: ['tactics', 'presets'], queryFn: tacticsApi.presets, staleTime: Infinity })
  const own = useQuery({ queryKey: ['tactics', 'team-plays', teamId], queryFn: () => teamPlaysApi.list(teamId) })
  const stars = useQuery({ queryKey: ['tactics', 'stars', teamId], queryFn: () => tacticStarsApi.list(teamId) })
  const star = useMutation({
    mutationFn: ({ key, on }: { key: string; on: boolean }) => tacticStarsApi.set(teamId, playKeyOf(key), on),
    onSuccess: (v) => qc.setQueryData(['tactics', 'stars', teamId], v),
  })
  const starred = stars.data?.play_keys.map(keyOf) ?? [] // 전술판 주소 키, 별표한 순서
  const canStar = !!stars.data?.can_edit
  const open = (k: string) => nav(`/tactics/${k}?team=${teamId}`) // team 은 댓글용
  const all: Play[] = [...(own.data?.items.map((v) => v.play) ?? []), ...(presets.data?.items ?? [])]
  const rest = (items: Play[]) => items.filter((p) => !starred.includes(p.key))
  const top = starred.map((k) => all.find((p) => p.key === k)).filter((p): p is Play => !!p)
  const row = { starred, canStar, onStar: (key: string, on: boolean) => star.mutate({ key, on }), onOpen: open }

  return (
    <div className="space-y-5">
      <FirstTimeTip id="tactics" />
      {top.length > 0 && (
        <section>
          <SectionTitle>별표 전술</SectionTitle>
          <PresetList items={top} {...row} />
        </section>
      )}

      <section>
        <SectionTitle action={<Link to={`/teams/${teamId}/plays/new`} className="text-sm font-semibold text-brand-ink">+ 새 전술 만들기</Link>}>우리 팀 전술</SectionTitle>
        {own.isLoading ? <Spinner /> : own.data?.items.length ? (
          rest(own.data.items.map((v) => v.play)).length ? <PresetList items={rest(own.data.items.map((v) => v.play))} {...row} /> : <p className="px-1 text-sm text-muted">모두 별표 전술에 있어요.</p>
        ) : (
          <p className="px-1 text-sm text-muted">코트 위에 다섯 명의 움직임을 그려 우리 팀만의 전술을 만들 수 있어요. 역할은 움직임에서 자동으로 붙고, AI가 자리마다 할 일을 풀어 줘요.</p>
        )}
      </section>

      <PresetGroup title="전술 목록" items={presets.data && rest(presets.data.items.filter((p) => p.situation === 'half_court'))} loading={presets.isLoading} row={row} />
      <PresetGroup
        title="인바운드" desc="골밑 베이스라인에서 공을 넣을 때 쓰는 전술이에요. 오늘 추천에는 들어가지 않아요."
        items={presets.data && rest(presets.data.items.filter((p) => p.situation === 'inbound'))} loading={presets.isLoading} row={row}
      />
      {star.isError && <p className="px-1 text-xs text-danger-ink">{star.error instanceof ApiError ? star.error.message : '별표를 바꾸지 못했어요.'}</p>}
    </div>
  )
}

type RowProps = { starred: string[]; canStar: boolean; onStar: (key: string, on: boolean) => void; onOpen: (key: string) => void }

function PresetGroup({ title, desc, items, loading, row }: { title: string; desc?: string; items?: Play[]; loading: boolean; row: RowProps }) {
  if (!loading && !items?.length) return null
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      {desc && <p className="-mt-1 mb-2 px-1 text-[11px] text-muted">{desc}</p>}
      {loading ? <Spinner /> : <PresetList items={items ?? []} {...row} />}
    </section>
  )
}

/** 전술 카드 목록. 매니저는 오른쪽 별을 눌러 별표를 달고 뗀다 (팀원에게는 별표한 것만 별이 보인다) */
function PresetList({ items, starred, canStar, onStar, onOpen }: { items: Play[] } & RowProps) {
  return (
    <div className="space-y-2">
      {items.map((p) => {
        const on = starred.includes(p.key)
        return (
          <div key={p.key} className="flex items-stretch rounded-2xl border border-line bg-surface shadow-[0_1px_2px_rgba(20,33,61,0.04)]">
            <button type="button" onClick={() => onOpen(p.key)} aria-label={`${p.name} 전술판 보기`} className="min-w-0 flex-1 space-y-1 rounded-2xl px-4 py-3 text-left active:bg-surface-2">
              <span className="flex items-center gap-2">
                <span className="font-semibold text-ink">{p.name}</span>
                {p.situation === 'half_court' && <Badge tone={p.defense === 'zone' ? 'navy' : 'neutral'}>{DEFENSE_LABEL[p.defense]}</Badge>}
              </span>
              <span className="block text-xs text-muted">{p.summary}</span>
            </button>
            {canStar ? (
              <button
                type="button" onClick={() => onStar(p.key, !on)} aria-pressed={on} aria-label={`${p.name} 별표${on ? ' 떼기' : ' 달기'}`}
                className={`flex w-12 shrink-0 items-center justify-center text-xl ${on ? 'text-court-500' : 'text-faint'}`}
              >
                {on ? '★' : '☆'}
              </button>
            ) : on ? (
              <span className="flex w-10 shrink-0 items-center justify-center text-lg text-court-500" aria-label="별표 전술">★</span>
            ) : (
              <span className="flex w-8 shrink-0 items-center justify-center text-faint" aria-hidden="true">›</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SquadLabel({ no, name, count, mine }: { no: number; name: string; count: number; mine: boolean }) {
  return (
    <div className="flex items-center gap-2 px-1 pt-1">
      <span className={`size-3 rounded-full ${squadStyle(no).dot}`} aria-hidden="true" />
      <span className="text-sm font-bold text-ink">{name}</span>
      <span className="text-xs text-muted">{count}명</span>
      {mine && <span className="text-xs font-semibold text-brand-ink">내 팀</span>}
    </div>
  )
}

/** 상대 수비 방식 토글 — 누를 때마다 맨투맨 ↔ 지역. 지금 켜진 쪽이 채워져 보인다 */
export function ZoneSwitch({ zone, setZone }: { zone: boolean; setZone: (z: boolean) => void }) {
  return (
    <button
      type="button" role="switch" aria-checked={zone} aria-label={`상대 수비: ${zone ? '지역 수비' : '맨투맨 수비'} (누르면 바뀜)`}
      onClick={() => setZone(!zone)}
      className="relative isolate inline-grid min-h-11 grid-cols-2 items-center rounded-full bg-sunken p-1 text-xs font-bold active:opacity-90"
    >
      <span
        className={`absolute inset-y-1 w-[calc(50%-4px)] rounded-full bg-surface shadow transition-transform ${zone ? 'translate-x-[calc(100%+0px)]' : 'translate-x-0'}`}
        style={{ left: 4 }} aria-hidden="true"
      />
      <span className={`relative z-10 px-3 py-1.5 transition-colors ${zone ? 'text-muted' : 'text-ink'}`}>맨투맨 수비</span>
      <span className={`relative z-10 px-3 py-1.5 transition-colors ${zone ? 'text-brand-ink' : 'text-muted'}`}>지역 수비</span>
    </button>
  )
}

function EventRecommend({ event, zone, setZone, rec, onlyMine = false, title }: {
  event: EventView; zone: boolean; setZone: (z: boolean) => void; rec: ReturnType<typeof useRecommendation>
  onlyMine?: boolean // 팀원은 내 팀 전술만 (일정 화면)
  title?: string
}) {
  const data = rec.data
  // 내 팀을 먼저. 팀원 화면에서는 내 팀만
  const squads = data
    ? [...data.squads]
      .filter((sq) => !onlyMine || data.can_edit || data.my_squad_no === null || sq.squad_no === data.my_squad_no)
      .sort((a, b) => Number(b.squad_no === data.my_squad_no) - Number(a.squad_no === data.my_squad_no))
    : []
  const single = squads.length === 1
  return (
    <section>
      <SectionTitle action={<ZoneSwitch zone={zone} setZone={setZone} />}>{title ?? `${mmdd(event.event_date)} 추천 전술`}</SectionTitle>
      {rec.isLoading ? <Spinner /> : !data ? <EmptyState title="추천을 불러오지 못했어요" /> : (
        <div className="space-y-4">
          {squads.map((sq) => (
            <SquadRecommend key={sq.squad_no} sq={sq} eventId={event.id} zone={zone} mine={sq.squad_no === data.my_squad_no} showLabel={!single} fitMin={data.fit_min} manager={data.can_edit} />
          ))}
        </div>
      )}
    </section>
  )
}

function SquadRecommend({ sq, eventId, zone, mine, showLabel, fitMin, manager }: {
  sq: SquadRecommendation; eventId: number; zone: boolean; mine: boolean; showLabel: boolean; fitMin: number; manager: boolean
}) {
  const ai = useAiTactics(eventId, sq.squad_no, zone, sq.items.length > 0)
  const aiOk = ai.data && !ai.data.fallback ? ai.data : null
  return (
    <div className="space-y-2">
      {showLabel && <SquadLabel no={sq.squad_no} name={sq.squad_name} count={sq.member_count} mine={mine} />}
      {sq.member_count < 5 ? (
        <p className="px-1 text-sm text-muted">5명 이상이어야 추천할 수 있어요.</p>
      ) : sq.items.length === 0 ? (
        <p className="rounded-2xl bg-surface px-4 py-3 text-sm text-muted">오늘 팀 구성으로는 적합도 {fitMin}를 넘는 전술이 없어요. 아래 목록에서 직접 골라 볼 수 있어요.</p>
      ) : (
        <>
          {ai.isLoading ? (
            <div className="px-1"><Thinking label="AI 코치가 전술을 읽고 있어요…" /></div>
          ) : aiOk?.one_liner && (
            <div className="border-l-2 border-brand pl-3">
              <p className="text-[11px] font-bold text-brand-ink">AI 코치</p>
              <TypedSections note={false} sections={[{ items: [aiOk.one_liner] }]} />
            </div>
          )}
          {sq.items.map((it, i) => (
            <LineupCard
              key={it.play_key} it={it} rank={i + 1} open={false} manager={manager}
              to={boardPath(it.play_key, eventId, sq.squad_no, zone)} ai={aiOk?.items.find((x) => x.play_key === it.play_key)}
            />
          ))}
        </>
      )}
    </div>
  )
}

/**
 * 전술 설명 한 덩어리 — 추천 카드와 전술판이 같이 쓴다.
 * AI 이유 · 핵심 자리 · 주의할 점(AI, 타자 효과) 과 막혔을 때의 대안(규칙, 그날 선수 이름) 을 한 섹션에.
 * AI 설명이 없으면(추천 밖 전술 · AI 실패) 전술 소개와 대안만.
 */
export function TacticExplain({ summary, ai, counter }: { summary: string; ai?: AiTacticItem; counter: string }) {
  return (
    <div className="space-y-2.5 rounded-2xl bg-surface-2 px-4 py-3">
      {ai ? (
        <TypedSections note={false} sections={[
          { items: [ai.reason], tone: 'lead' },
          { title: '핵심 자리', items: ai.key_roles },
          { title: '주의할 점', items: ai.caution ? [ai.caution] : [], tone: 'caution' },
        ]} />
      ) : (
        <p className="text-[15px] font-semibold leading-snug text-ink">{summary}</p>
      )}
      {counter && (
        <div>
          <p className="mb-1 text-xs font-bold text-muted">막히면</p>
          <p className="text-sm leading-relaxed text-ink-2">{counter}</p>
        </div>
      )}
      {ai && <p className="text-[11px] text-faint">이유와 핵심 자리는 AI가 썼어요 · 전술과 자리는 앱이 골랐어요</p>}
    </div>
  )
}

/** "허재" + 아래 줄에 "예비 양동근 · 김승현" */
export function SlotPeople({ s }: { s: SlotLineup }) {
  return (
    <span className="block min-w-0">
      <span className="block truncate font-semibold text-ink">{s.display_name}</span>
      {s.backups.length > 0 && <span className="block truncate text-xs text-muted">예비 {s.backups.map((b) => b.display_name).join(' · ')}</span>}
    </span>
  )
}

function LineupCard({ it, rank, open: initial, to, manager, ai }: { it: PlayLineup; rank: number; open: boolean; to: string; manager: boolean; ai?: AiTacticItem }) {
  const nav = useNavigate()
  const [open, setOpen] = useState(initial)
  const [why, setWhy] = useState(false)
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <button type="button" onClick={() => setOpen(!open)} className="flex min-h-14 w-full items-center gap-3 px-4 text-left" aria-expanded={open}>
        <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-black ${rank === 1 ? 'bg-brand text-on-brand' : 'bg-sunken text-muted'}`}>{rank}</span>
        <span className="min-w-0 flex-1 truncate font-bold text-ink">{it.name}</span>
        {it.manual && <Badge tone="navy">매니저 배치</Badge>}
        <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-xs font-bold text-brand-ink">적합도 {Math.round(it.fit)}</span>
        <span className="text-faint" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-line px-4 pb-4 pt-3">
          <TacticExplain summary={it.summary} ai={ai} counter={it.counter} />
          <ul className="divide-y divide-line">
            {it.slots.map((s) => (
              <li key={s.slot} className="flex items-center gap-3 py-2">
                <span className="w-5 shrink-0 text-center text-sm font-bold text-brand-ink">{CIRCLED[s.slot - 1]}</span>
                <span className="w-[5.5rem] shrink-0 text-sm text-ink-2">{ROLE_LABEL[s.role]}</span>
                <span className="min-w-0 flex-1 text-sm"><SlotPeople s={s} /></span>
                {manager && s.score !== null && <span className="shrink-0 text-xs tabular-nums text-muted">{s.score}</span>}
              </li>
            ))}
          </ul>
          {manager && (
            <div>
              <button type="button" onClick={() => setWhy(!why)} className="text-xs font-semibold text-muted underline-offset-2 active:underline">
                {why ? '선수별 근거 접기' : '선수별 근거 보기 (매니저만)'}
              </button>
              {why && (
                <ul className="mt-1.5 space-y-1">
                  {it.slots.map((s) => (
                    <li key={s.slot} className="text-[11px] leading-relaxed text-muted">
                      <b className="text-ink-2">{s.display_name}</b>
                      {s.matched_attrs.length > 0 && <> · {s.matched_attrs.slice(0, 3).join(' · ')}</>}
                      {s.missing_attrs.length > 0 && <span className="text-warn-ink"> · 부족: {s.missing_attrs.join(' · ')}</span>}
                      {s.alt_display_name && <> · 벤치 교체 후보 {s.alt_display_name}</>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <button
            type="button" onClick={() => nav(to)}
            className="flex min-h-11 w-full items-center justify-center gap-1 rounded-xl bg-brand text-sm font-semibold text-on-brand active:opacity-90"
          >
            전술판에서 보기{manager ? ' · 자리 바꾸기' : ''} <span aria-hidden="true">→</span>
          </button>
        </div>
      )}
    </div>
  )
}

/** 일정 화면(배정 확정 뒤)의 추천 전술 — 팀 배정 결과 바로 아래. 팀원은 내 팀 것만, 매니저는 모든 팀 (2팀 · 3팀) */
export function EventTactics({ event }: { event: EventView }) {
  const [zone, setZone] = useState(false)
  const rec = useRecommendation(event.id, zone)
  if (rec.error instanceof ApiError && rec.error.status === 403) return null
  return <EventRecommend event={event} zone={zone} setZone={setZone} rec={rec} onlyMine title="이 팀에 맞는 전술" />
}
