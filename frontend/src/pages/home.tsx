/** S-04 홈 (역할별) · S-17 내 프로필 · 내 팀 목록. */
import { useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { authApi, ME_STALE } from '../api/auth'
import { eventsApi } from '../api/events'
import { teamsApi } from '../api/teams'
import { localISODate, type EventView, type Page } from '../api/types'
import { errorMessage } from '../api/client'
import { Badge, Button, Card, EmptyState, LoadError, RoleBadge, SectionTitle, Spinner, TeamStatusBadge } from '../components/ui'
import { confirm, toast } from '../store/feedback'
import { TutorialCard, TutorialPrompt } from '../components/tutorial'
import { Content, Screen, TabBar, TopBar } from '../components/layout'
import { fmtEvent } from '../lib/format'
import { invalidateEvent } from '../lib/invalidate'
import { josa } from '../lib/josa'

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: authApi.me, staleTime: ME_STALE })
}
export function useMyTeams() {
  return useQuery({ queryKey: ['me', 'teams'], queryFn: authApi.myTeams, staleTime: ME_STALE })
}

/** 내 모든 팀의 아직 진행하지 않은 일정 (가까운 순). 지난 일정은 팀 화면 일정 탭에서 본다 */
function useUpcoming(teamIds: number[]) {
  const today = localISODate()
  // 오늘 이후만 서버에서 거른다 — 지난 일정까지 50개씩 받아 버리지 않게
  const results = useQueries({
    queries: teamIds.map((id) => ({ queryKey: ['events', 'team', id, 'upcoming', today], queryFn: () => eventsApi.list(id, { size: 50, from: today }) })),
  })
  const upcoming: EventView[] = results
    .flatMap((r) => r.data?.items ?? [])
    .filter((e) => e.status !== 'CANCELED' && e.event_date >= today)
    .sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  const failed = results.filter((r) => r.isError)
  return {
    upcoming, isLoading: results.some((r) => r.isLoading),
    // 일부 팀만 실패해도 알린다 — "예정된 일정이 없어요" 로 오해하지 않게
    error: failed[0]?.error ?? null,
    retry: () => failed.forEach((r) => r.refetch()),
    retrying: failed.some((r) => r.isFetching),
  }
}

const SKIP_KEY = 'hooply-unrecorded-skip'
function readSkipped(): number[] {
  try { return JSON.parse(localStorage.getItem(SKIP_KEY) ?? '[]') as number[] } catch { return [] }
}

/**
 * 매니저의 경기 후 할 일 — 내가 매니저인 팀마다 최근 일정을 한 번씩만 받아, 팀마다 **가장 최근에 끝난 일정**에 기록이 없을 때만.
 * 그 뒤 일정을 기록했으면 옛 일정을 몇 달씩 붙들고 있지 않는다. "기록 안 함"으로 닫은 일정은 이 기기에서 다시 묻지 않는다 (docs/09 3-11)
 */
function useUnrecorded(managerTeamIds: number[]) {
  const results = useQueries({
    queries: managerTeamIds.map((id) => ({ queryKey: ['events', 'team', id, 'recent', 20], queryFn: () => eventsApi.list(id, { size: 20 }) })),
  })
  const [skipped, setSkipped] = useState(readSkipped)
  const skip = (eventId: number) => {
    const next = [...skipped.filter((x) => x !== eventId), eventId].slice(-50)
    setSkipped(next)
    try { localStorage.setItem(SKIP_KEY, JSON.stringify(next)) } catch { /* 저장 못 해도 이번 화면에서는 닫힌다 */ }
  }
  const event = results
    .map((r) => (r.data?.items ?? [])
      .filter((e) => e.status !== 'CANCELED' && (e.status === 'DONE' || e.survey_open))
      .sort((a, b) => b.event_date.localeCompare(a.event_date) || (b.start_time ?? '').localeCompare(a.start_time ?? ''))[0])
    // 10명이 안 모인 날은 기록할 수 없으니 묻지 않는다
    .filter((e) => e && e.quarter_count === 0 && e.attend_count >= 10 && !skipped.includes(e.id))
    .sort((a, b) => b!.event_date.localeCompare(a!.event_date))[0]
  return { event, skip }
}

export function HomePage() {
  const me = useMe()
  const teams = useMyTeams()
  const primaryId = me.data?.primary_team_id ?? null
  const teamList = [...(teams.data?.items ?? [])].sort((a, b) => Number(b.team_id === primaryId) - Number(a.team_id === primaryId))  // 기본 팀이 맨 위
  const upcoming = useUpcoming(teamList.map((t) => t.team_id))
  const nameOf = (id: number) => teamList.find((t) => t.team_id === id)?.team_name
  const isManagerSomewhere = teamList.some((t) => t.role === 'MANAGER')
  const next = upcoming.upcoming[0]
  const { event: unrecorded, skip: skipUnrecorded } = useUnrecorded(teamList.filter((t) => t.role === 'MANAGER').map((t) => t.team_id))

  return (
    <Screen>
      <TopBar tone="navy" title={<span className="flex items-center gap-2"><span className="flex size-6 items-center justify-center rounded-md bg-brand text-[12px] font-black text-on-brand">H</span><span className="tracking-[0.12em]">HOOPLY</span></span>} />
      <Content>
        <div className="rounded-2xl bg-bar p-5 text-bar-ink">
          <p className="text-sm text-bar-sub">안녕하세요,</p>
          <p className="text-xl font-bold">{me.data ? `${me.data.nickname ?? me.data.name}님` : '…'}</p>
          {me.data && !me.data.onboarding_completed && me.data.tutorial_state !== 'ACTIVE' ? (  /* 시작 안내 중이면 체크리스트가 대신 안내한다 */
            <Link to="/survey" className="mt-3 flex min-h-11 items-center justify-between rounded-xl border border-brand-line bg-brand-soft px-4 py-3 text-sm font-semibold text-brand-ink">
              실력 설문을 아직 안 하셨어요 · 2분이면 끝나요 <span>→</span>
            </Link>
          ) : null}
          {unrecorded && (
            <div className="mt-3 flex min-h-11 items-center gap-1 rounded-xl bg-white/10 pl-4 pr-1 text-sm">
              <span className="min-w-0 flex-1 truncate">{Number(unrecorded.event_date.slice(5, 7))}/{Number(unrecorded.event_date.slice(8, 10))} 기록이 없어요</span>
              <Link to={`/events/${unrecorded.id}/quarters`} state={{ from: '/' }} className="flex min-h-11 shrink-0 items-center px-2 font-bold underline underline-offset-2">기록하기</Link>
              <button type="button" onClick={() => skipUnrecorded(unrecorded.id)} className="min-h-11 shrink-0 px-2 text-xs text-bar-sub">기록 안 함</button>
            </div>
          )}
          {me.data && !me.data.onboarding_completed && me.data.tutorial_state !== 'ACTIVE' ? null : next ? <NextEvent e={next} teamName={nameOf(next.team_id)} /> : null}
        </div>

        {me.data && <TutorialCard me={me.data} />}
        {me.data && <TutorialPrompt me={me.data} />}

        <GuestClaimCards />

        <section>
          <SectionTitle>다가오는 일정</SectionTitle>
          {upcoming.error && <div className="mb-2"><LoadError message={errorMessage(upcoming.error, '일정을 불러오지 못했어요.')} onRetry={upcoming.retry} retrying={upcoming.retrying} /></div>}
          {upcoming.isLoading || teams.isLoading ? <Spinner /> : upcoming.upcoming.length ? (
            <div className="space-y-2">
              {upcoming.upcoming.map((e) => <EventRow key={e.id} e={e} teamName={nameOf(e.team_id)} />)}
            </div>
          ) : upcoming.error || teams.isError ? null : (
            <EmptyState title="예정된 일정이 없어요" desc={isManagerSomewhere ? '팀 화면에서 일정을 등록해 주세요.' : '매니저가 일정을 올리면 여기에 보여요.'} />
          )}
        </section>

        <section>
          <SectionTitle>내 팀</SectionTitle>
          {teams.isLoading ? <Spinner /> : teams.isError && !teams.data ? (
            // 내 팀을 못 받았는데 "팀이 없어요 → 만들기" 를 보여 주면 이미 팀이 있는 사람이 팀을 또 만든다
            <LoadError message={errorMessage(teams.error, '내 팀을 불러오지 못했어요.')} onRetry={() => teams.refetch()} retrying={teams.isFetching} />
          ) : teamList.length ? (
            <div className="space-y-2">
              {teamList.map((t) => <TeamRow key={t.team_id} {...t} primary={teamList.length > 1 ? (me.data?.primary_team_id ?? teamList[0].team_id) === t.team_id : null} />)}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Link to="/teams/join" className="flex min-h-11 items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface/60 text-sm font-semibold text-ink-2">+ 팀 코드로 가입</Link>
                <Link to="/teams/new" className="flex min-h-11 items-center justify-center rounded-xl border border-dashed border-line-strong bg-surface/60 text-sm font-semibold text-ink-2">+ 팀 만들기</Link>
              </div>
            </div>
          ) : (
            <EmptyState title="아직 소속된 팀이 없어요" desc="팀 코드를 받았다면 가입하고, 없다면 직접 만들어 주세요."
              action={<div className="flex gap-2"><Link to="/teams/join"><Button variant="secondary">코드로 가입</Button></Link><Link to="/teams/new"><Button>팀 만들기</Button></Link></div>}
            />
          )}
        </section>
      </Content>
      <TabBar />
    </Screen>
  )
}

/**
 * 홈에서 바로 응답 (docs/10 F-2) — 일정 화면의 응답과 같은 API · 같은 순서 보장(scope)을 쓴다.
 * 이 팀의 일정 목록 캐시를 먼저 바꿔 누르는 즉시 바뀐 것처럼 보여 주고, 실패하면 되돌린다.
 */
function useQuickRsvp(e: EventView) {
  const qc = useQueryClient()
  const lists = ['events', 'team', e.team_id]
  const key = ['rsvp', e.id]
  return useMutation({
    mutationKey: key,
    mutationFn: (status: 'ATTEND' | 'ABSENT') => eventsApi.respond(e.id, status),
    scope: { id: `rsvp-${e.id}` },  // 연달아 눌러도 순서대로 보낸다
    onMutate: async (status) => {
      await qc.cancelQueries({ queryKey: lists })
      const prev = qc.getQueriesData<unknown>({ queryKey: lists })
      // 같은 접두어 아래에 일정 목록이 아닌 캐시(리더보드 기간 · 팀 화면의 이어 받기)도 있어, 일정 목록 모양일 때만 바꾼다
      qc.setQueriesData<Page<EventView>>({ queryKey: lists }, (old) => !old || !Array.isArray(old.items) ? old : {
        ...old,
        items: old.items.map((x) => x.id !== e.id || !('my_attendance' in x) ? x
          : { ...x, my_attendance: status, attend_count: x.attend_count + (status === 'ATTEND' ? 1 : 0) - (x.my_attendance === 'ATTEND' ? 1 : 0) }),
      })
      return { prev }
    },
    onError: (err, _status, ctx) => {
      ctx?.prev.forEach(([k, data]) => qc.setQueryData(k, data))
      toast(errorMessage(err, '응답하지 못했어요.'), 'error')
    },
    // 연달아 누르면 아직 보낼 응답이 남아 있다(자기 자신도 센다) — 마지막 것만 다시 받는다. 시작 안내의 "참석 응답" 단계도 여기서 끝난다
    onSettled: () => {
      if (qc.isMutating({ mutationKey: key }) > 1) return
      invalidateEvent(qc, e.id, e.team_id)
      qc.invalidateQueries({ queryKey: ['me', 'tutorial'] })
    },
  })
}

/** 홈 위쪽의 "다음 일정". 응답을 받는 중이면 일정 화면까지 가지 않고 여기서 참석 · 불참을 고른다 — 고른 쪽이 눌린 채로 남아 다시 바꿀 수 있다 */
function NextEvent({ e, teamName }: { e: EventView; teamName?: string }) {
  const respond = useQuickRsvp(e)
  const mine = e.my_attendance
  return (
    <div className="mt-3 rounded-xl bg-white/10">
      <Link to={`/events/${e.id}`} state={{ from: '/' }} className="flex min-h-11 items-center justify-between px-4 py-3">
        <div className="min-w-0">
          <p className="text-[11px] text-bar-sub">다음 일정 {dday(e.event_date)}{teamName ? ` · ${teamName}` : ''}</p>
          <p className="truncate text-sm font-bold">{fmtEvent(e)}{e.venue ? ` · ${e.venue}` : ''}</p>
        </div>
        {e.rsvp_open ? (
          // 응답은 아래 버튼이 보여 준다. 아직 안 했으면 눈에 띄게, 했으면 "자세히" 화살표만
          mine === 'ATTEND' || mine === 'ABSENT' ? <span aria-hidden className="ml-2 shrink-0 text-bar-sub">→</span>
            : <span className="ml-2 shrink-0 rounded-full bg-warn-soft px-2.5 py-1 text-[11px] font-bold text-warn-ink">미응답</span>
        ) : (
          <span className={`ml-2 shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${mine === 'ATTEND' ? 'bg-brand text-on-brand' : 'bg-white/10 text-bar-sub'}`}>
            {mine === 'ATTEND' ? '참석' : mine === 'ABSENT' ? '불참' : '응답 마감'}
          </span>
        )}
      </Link>
      {e.rsvp_open && (
        <div role="group" aria-label="참석 응답" className="grid grid-cols-2 gap-2 px-3 pb-3">
          {(['ATTEND', 'ABSENT'] as const).map((st) => {
            const on = mine === st
            return (
              <button
                key={st} type="button" aria-pressed={on}
                onClick={() => { if (!on) respond.mutate(st) }}
                className={`min-h-11 rounded-lg border text-sm font-bold transition ${
                  on ? (st === 'ATTEND' ? 'border-brand bg-brand text-on-brand' : 'border-bar-ink bg-bar-ink text-bar') : 'border-white/30 text-bar-ink'
                }`}
              >
                {st === 'ATTEND' ? '참석' : '불참'}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function EventRow({ e, teamName, withDetail, past }: { e: EventView; teamName?: string; withDetail?: boolean; past?: boolean }) {
  const nav = useNavigate()
  const my = e.my_attendance
  return (
    <Card onClick={() => nav(`/events/${e.id}`, { state: { from: window.location.pathname } })} label={`${e.title ?? fmtEvent(e)} 일정 열기`} className={`flex items-center gap-3 ${withDetail ? 'rounded-b-none' : ''} ${past ? 'opacity-75' : ''}`}>
      <div className={`flex size-12 flex-col items-center justify-center rounded-xl ${past ? 'bg-sunken text-muted' : 'bg-info-soft text-ink'}`}>
        <span className="text-[10px] leading-none">{Number(e.event_date.slice(5, 7))}월</span>
        <span className="text-lg font-black leading-tight">{Number(e.event_date.slice(8, 10))}</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-bold text-ink">{e.title ?? fmtEvent(e)}</p>
        <p className="truncate text-xs text-muted">{teamName ? `${teamName} · ` : ''}{fmtEvent(e)}{e.venue ? ` · ${e.venue}` : ''}</p>
        {e.my_squad_name && !withDetail && <p className="text-xs font-semibold text-brand-ink">배정 확정 · {e.my_squad_name}{e.my_assigned_position ? ` ${e.my_assigned_position}` : ''}</p>}
      </div>
      <div className="flex flex-col items-end gap-1">
        {e.status === 'CANCELED' ? <Badge>취소됨</Badge> : my === 'ATTEND' ? <Badge tone="success">참석</Badge> : my === 'ABSENT' ? <Badge>불참</Badge> : <Badge tone="warn">미응답</Badge>}
        <span className="text-[11px] text-muted">참석 {e.attend_count}</span>
      </div>
    </Card>
  )
}

/** 팀 카드. 팀이 둘 이상이면 "기본" 표시와 "기본 팀으로" 버튼 — 목록 맨 위·프로필이 먼저 보여줄 팀 */
function TeamRow(t: { team_id: number; team_name: string; team_status: 'PENDING' | 'ACTIVE' | 'ARCHIVED'; approval_status: 'PENDING' | 'APPROVED' | 'REJECTED'; role: 'MANAGER' | 'PLAYER'; member_count: number; primary: boolean | null }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const setPrimary = useMutation({
    mutationFn: () => authApi.updateMe({ primary_team_id: t.team_id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['me'] }); toast(`${t.team_name}${josa(t.team_name, '을')} 기본 팀으로 정했어요.`) },
    onError: (e) => toast(errorMessage(e, '기본 팀을 바꾸지 못했어요.'), 'error'),
  })
  // "기본 팀으로" 는 카드 밖에 둔다 — 카드 안에 두면 터치 영역(44px)이 카드 가운데를 덮어, 팀을 열려다 기본 팀이 바뀐다
  return (
    <div>
      <Card onClick={() => nav(`/teams/${t.team_id}`)} label={`${t.team_name} 팀 열기`} className="flex items-center gap-3">
        <span className="flex size-11 items-center justify-center rounded-xl bg-brand-soft text-base font-black text-brand-ink">{t.team_name.slice(0, 1)}</span>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 truncate font-bold text-ink">{t.team_name}{t.primary && <Badge tone="court">기본</Badge>}</p>
          <p className="text-xs text-muted">팀원 {t.member_count}명</p>
        </div>
        <div className="flex flex-col items-end gap-1"><RoleBadge role={t.role} /><TeamStatusBadge status={t.team_status} approval={t.approval_status} /></div>
      </Card>
      {t.primary === false && (
        <div className="-mb-2 flex items-center justify-end gap-1 pl-1">
          <span className="min-w-0 truncate text-xs text-muted">{t.team_name}</span>
          <button type="button" onClick={() => setPrimary.mutate()} disabled={setPrimary.isPending} aria-label={`${t.team_name} 기본 팀으로`} className="min-h-11 shrink-0 px-2 text-xs font-semibold text-ink-2 underline underline-offset-2 disabled:opacity-50">
            기본 팀으로
          </button>
        </div>
      )}
    </div>
  )
}

function dday(date: string) {
  const diff = Math.round((new Date(date + 'T00:00:00').getTime() - new Date(new Date().toDateString()).getTime()) / 86_400_000)
  return diff <= 0 ? 'D-DAY' : `D-${diff}`
}

/**
 * "지난 일정에 게스트로 온 기록이 있어요. 본인이 맞나요?" — 같은 이름의, 아직 이어 주지 않은 게스트가 있을 때만 보인다.
 * 맞다고 하면 그 팀의 내 기록으로 이어받고(매니저의 기록 이어 주기와 같은 처리), 아니라고 하면 다시 묻지 않는다.
 */
export function GuestClaimCards({ teamId }: { teamId?: number } = {}) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['me', 'guest-claims'], queryFn: teamsApi.myGuestClaims })
  const [busy, setBusy] = useState<number | null>(null)
  const decide = useMutation({
    mutationFn: ({ gid, accept }: { gid: number; accept: boolean }) => teamsApi.claimGuest(gid, accept),
    onMutate: ({ gid }) => setBusy(gid),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ['me'] }); qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['stats'] }); qc.invalidateQueries({ queryKey: ['team'] })
      toast(v.accept ? '기록을 이어받았어요. 프로필의 기록에서 볼 수 있어요.' : '알겠어요. 다시 묻지 않을게요.')
    },
    onError: (e) => toast(errorMessage(e, '저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.'), 'error'),
    onSettled: () => setBusy(null),
  })
  const items = (q.data?.items ?? []).filter((c) => teamId === undefined || c.team_id === teamId)
  if (items.length === 0) return null
  return (
    <div className="space-y-2">
      {items.map((c) => (
        <Card key={c.guest.id} className="border-brand-line bg-brand-soft">
          <p className="text-sm font-bold text-ink">지난 일정에 게스트로 온 기록이 있어요. 본인이 맞나요?</p>
          <p className="mt-1 text-sm text-ink-2">
            <b>{c.team_name}</b>에 게스트 <b>{c.guest.display_name}</b>{josa(c.guest.display_name, '으로')} 참석 {c.events_attended}회 · 출전 {c.quarters_played}쿼터
            {c.last_event_date ? ` · 마지막 ${Number(c.last_event_date.slice(5, 7))}/${Number(c.last_event_date.slice(8, 10))}` : ''}
          </p>
          <p className="mt-1 text-xs text-muted">맞으면 그 기록을 내 기록으로 이어받아요. 아니면 다시 묻지 않아요.</p>
          <div className="mt-3 flex flex-col-reverse gap-1">
            <Button variant="ghost" full className="text-sm" disabled={busy === c.guest.id} onClick={() => decide.mutate({ gid: c.guest.id, accept: false })}>내 기록이 아니에요</Button>
            <Button full variant="secondary" className="text-sm" loading={busy === c.guest.id} onClick={async () => { if (await confirm({ title: '내 기록으로 이어받을까요?', body: `${c.team_name}의 게스트 ${c.guest.display_name} 기록(참석 ${c.events_attended}회 · 출전 ${c.quarters_played}쿼터)을 내 기록으로 이어받아요.`, confirmLabel: '기록 이어받기' })) decide.mutate({ gid: c.guest.id, accept: true }) }}>내 기록이 맞아요 · 이어받기</Button>
          </div>
        </Card>
      ))}
    </div>
  )
}
