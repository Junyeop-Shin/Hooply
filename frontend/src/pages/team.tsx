/** S-05 팀 생성 · S-06 팀 가입 · S-07 팀 상세 · S-08 팀원 관리 (FR-04 ~ FR-07). */
import { useState, type FormEvent } from 'react'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, errorMessage as errMsg } from '../api/client'
import { teamsApi } from '../api/teams'
import { eventsApi } from '../api/events'
import { EventRow, GuestClaimCards, useMe } from './home'
import { announceShare, copyText, shareText } from '../lib/kakao'
import { confirm, toast } from '../store/feedback'
import { AdoptedSummary } from '../components/adopted'
import { surveyApi } from '../api/survey'
import { localISODate, type PlayerCard, type PlayerCardDetailed, type TeamDetail } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, EmptyState, Field, GradeDot, LoadError, RoleBadge, SectionTitle, Spinner, TeamStatusBadge } from '../components/ui'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { RecordsTab } from '../components/records'
import { TacticsTab } from '../components/tactics'

const EVENTS_PAGE = 5
/** 일정 탭이 서버에서 한 번에 받는 일정 수. 더 있으면(meta.has_next) "지난 일정 더 불러오기" 로 다음 묶음을 받는다 */
const EVENTS_FETCH = 50
type TeamTab = 'events' | 'records' | 'tactics' | 'members'
const seenMonthKey = (teamId: number) => `hooply:records-seen-month:${teamId}`

/**
 * 첫 탭 결정. 평소엔 일정 탭. 달이 바뀐 뒤 처음 팀 화면을 열면 딱 한 번 기록 탭을 먼저 보여 준다 —
 * 지난달 월간 랭킹이 확정됐다는 뜻이라서. "지난 방문 달" 을 이 기기에 기억하고, 없으면(첫 방문) 그냥 적어만 둔다.
 */
function initialTab(teamId: number): { tab: TeamTab; newMonth: boolean } {
  const cur = localISODate().slice(0, 7)
  try {
    const seen = localStorage.getItem(seenMonthKey(teamId))
    localStorage.setItem(seenMonthKey(teamId), cur)
    if (seen && seen !== cur) return { tab: 'records', newMonth: true }
  } catch { /* 저장소를 못 쓰면 늘 일정 탭 */ }
  return { tab: 'events', newMonth: false }
}

/* ---------- S-05 팀 생성 ---------- */
export function TeamCreatePage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', description: '', home_court: '' })
  const [created, setCreated] = useState<{ id: number; team_code: string } | null>(null)
  const m = useMutation({
    mutationFn: () => teamsApi.create({ name: form.name, description: form.description || undefined, home_court: form.home_court || undefined }),
    onSuccess: (res) => { setCreated(res); qc.invalidateQueries({ queryKey: ['me', 'teams'] }) },
    meta: { inlineError: true },
  })

  if (created) {
    return (
      <Screen>
        <TopBar title="팀이 만들어졌어요" />
        <Content className="flex flex-col items-center justify-center text-center">
          <p className="text-lg font-bold text-ink">{form.name}</p>
          <p className="text-sm text-muted">아래 코드를 팀원에게 공유하세요. 관리자 승인이 끝나고 5명이 모이면 일정을 만들 수 있어요.</p>
          <Alert kind="info">새 팀은 관리자 확인 후 승인돼요. 보통 하루 안에 처리되고, 그동안 팀원 모집은 계속할 수 있어요.</Alert>
          <TeamCodeBox code={created.team_code} teamName={form.name} />
        </Content>
        <BottomAction>
          <Button full onClick={() => nav(`/teams/${created.id}`, { replace: true })}>팀으로 이동</Button>
        </BottomAction>
      </Screen>
    )
  }

  return (
    <Screen>
      <TopBar title="팀 만들기" back="/" />
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate() }} className="flex flex-1 flex-col">
        <Content>
          <div data-tutorial="CREATE_TEAM"><Field label="팀 이름" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="화요농구" maxLength={50} required /></div>
          <Field label="소개 (선택)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="매주 화요일 8시, 초보 환영" />
          <Field label="홈 코트 (선택)" value={form.home_court} onChange={(e) => setForm({ ...form, home_court: e.target.value })} placeholder="서초체육관" maxLength={100} />
          {m.isError && <Alert>{errMsg(m.error, '팀을 만들지 못했어요.')}</Alert>}
          <Alert kind="info">팀을 만든 사람이 매니저가 돼요. 나중에 다른 팀원에게 권한을 넘길 수 있어요.</Alert>
        </Content>
        <BottomAction><div data-tutorial="CREATE_TEAM"><Button type="submit" full loading={m.isPending}>팀 코드 발급받기</Button></div></BottomAction>
      </form>
    </Screen>
  )
}

/** 팀 코드 공유 문구 + 가입 링크 (S-06 이 ?code= 로 코드를 미리 채운다) */
export const teamInviteText = (name: string, code: string) => ({
  text: `[HOOPLY] ${name} 팀에 초대해요.\n팀 코드 ${code} 를 넣고 가입해 주세요.`,
  url: `${window.location.origin}/teams/join?code=${code}`,
})

/** 팀 코드 공유 — 코드 복사 · 카카오톡 공유 결과는 어디서나 토스트로 (lib/kakao) */
const shareInvite = async (teamName: string, code: string) => { const { text, url } = teamInviteText(teamName, code); announceShare(await shareText(text, url)) }

function TeamCodeBox({ code, teamName }: { code: string; teamName: string }) {
  const copy = () => copyText(code, '팀 코드를 복사했어요.')
  const share = () => shareInvite(teamName, code)
  return (
    <div className="mt-2 w-full rounded-2xl border-2 border-dashed border-court-300 bg-brand-soft p-4">
      <p className="text-xs font-semibold text-brand-ink">팀 코드</p>
      <p className="my-1 font-mono text-3xl font-black tracking-[0.3em] text-ink">{code}</p>
      <div className="flex justify-center gap-2">
        <Button variant="secondary" onClick={copy} className="text-sm">복사</Button>
        <button onClick={share} className="min-h-11 rounded-xl bg-[#FEE500] px-4 text-sm font-semibold text-[#191919] active:brightness-95">카카오톡 공유</button>
      </div>
    </div>
  )
}

/* ---------- S-06 팀 가입 ---------- */
export function TeamJoinPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [code, setCode] = useState(() => (new URLSearchParams(window.location.search).get('code') ?? '').toUpperCase().slice(0, 8))  // 초대 링크 ?code= 미리 채움
  const m = useMutation({
    mutationFn: () => teamsApi.join(code.trim().toUpperCase()),
    onSuccess: (team) => { qc.invalidateQueries({ queryKey: ['me', 'teams'] }); qc.invalidateQueries({ queryKey: ['profile'] }); nav(`/teams/${team.id}/self-rank`, { replace: true, state: { from: `/teams/${team.id}` } }) },
    meta: { inlineError: true },  // 아래 Alert 가 서버 문구(제외된 팀 재가입 403 등)를 그대로 보여 준다
  })
  const err = m.error instanceof ApiError ? m.error : null
  return (
    <Screen>
      <TopBar title="팀 코드로 가입" back="/" />
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate() }} className="flex flex-1 flex-col">
        <Content>
          <div data-tutorial="JOIN_TEAM"><Field
            label="팀 코드"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABCD2345"
            maxLength={8}
            autoCapitalize="characters"
            className="font-mono text-2xl tracking-[0.3em] uppercase"
            error={err?.code === 'TEAM_CODE_NOT_FOUND' ? '존재하지 않거나 만료된 코드예요.' : undefined}
            hint="매니저가 카카오톡으로 보내준 8자리 코드"
            required
          /></div>
          {/* 서버 문구 그대로 — 제외된 팀에 다시 가입하면 403 과 함께 이유가 온다 */}
          {err && err.code !== 'TEAM_CODE_NOT_FOUND' && (
            <Alert kind={err.code === 'ALREADY_MEMBER' ? 'info' : 'error'}>{err.message}</Alert>
          )}
          {m.isError && !err && <Alert>{errMsg(m.error, '가입하지 못했어요. 잠시 뒤 다시 시도해 주세요.')}</Alert>}
        </Content>
        <BottomAction><div data-tutorial="JOIN_TEAM"><Button type="submit" full loading={m.isPending} disabled={code.length !== 8}>가입하기</Button></div></BottomAction>
      </form>
    </Screen>
  )
}

/* ---------- S-07 팀 상세 ---------- */
export function TeamDetailPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const nav = useNavigate()
  const [{ tab, newMonth }, setTabState] = useState(() => initialTab(id))
  const setTab = (t: TeamTab) => setTabState((s) => ({ ...s, tab: t }))
  const team = useQuery({ queryKey: ['team', id], queryFn: () => teamsApi.get(id) })
  const players = useQuery({ queryKey: ['team', id, 'players'], queryFn: () => teamsApi.players(id), enabled: tab === 'members' })
  // 최신순 50개씩. 예정 일정은 날짜가 가장 늦어 첫 묶음에 들어오고, 오래된 지난 일정은 "더 불러오기" 로 받는다
  const events = useInfiniteQuery({
    queryKey: ['events', 'team', id, 'pages'],
    queryFn: ({ pageParam }) => eventsApi.list(id, { size: EVENTS_FETCH, page: pageParam }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.meta.has_next ? last.meta.page + 1 : undefined),
    enabled: tab === 'events',
  })
  const profile = useQuery({ queryKey: ['profile'], queryFn: surveyApi.myProfile })
  const myTeamProfile = profile.data?.teams.find((t) => t.team_id === id)
  const today = localISODate()
  const [page, setPage] = useState(0)
  // 아직 진행하지 않은 일정(가까운 순)이 먼저, 그 뒤에 지난 일정(최근 순). 5개씩 페이지
  const fetched = events.data?.pages.flatMap((p) => p.items) ?? []
  const all = fetched.filter((e, i) => e.status !== 'CANCELED' && fetched.findIndex((x) => x.id === e.id) === i)  // 묶음 사이에 새 일정이 끼면 겹칠 수 있다
  const upcomingList = all.filter((e) => e.event_date >= today).sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  const pastList = all.filter((e) => e.event_date < today).sort((a, b) => b.event_date.localeCompare(a.event_date))
  const sortedEvents = [...upcomingList, ...pastList]
  // 확정 요약은 가장 가까운 확정 일정 하나만 — 일정마다 배정 결과를 따로 부르지 않게
  const nextAdoptedId = sortedEvents.find((e) => e.adopted_candidate_id && e.event_date >= today)?.id
  const upcomingCount = upcomingList.length

  if (team.isLoading) return <Screen><TopBar title="팀" back="/" /><Spinner /></Screen>
  if (team.isError || !team.data) {
    return <Screen><TopBar title="팀" back="/" /><Content><Alert>{errMsg(team.error, '팀을 불러오지 못했어요.')}</Alert></Content></Screen>
  }
  const t = team.data
  const isManager = t.my_role === 'MANAGER'
  const need = Math.max(0, t.min_members - t.member_count)

  return (
    <Screen>
      <TopBar tone="navy" title={t.name} back="/" right={isManager && <Link to={`/teams/${id}/members`} className="-mr-1 flex min-h-11 items-center px-2 text-sm font-semibold text-court-300">팀 관리</Link>} />
      <div className="bg-navy-800 px-4 pb-4 text-white">
        <div className="flex items-center gap-2 text-sm text-bar-sub">
          <span>팀원 {t.member_count}명</span>·<span>{t.home_court ?? '홈 코트 미정'}</span>
          <span className="ml-auto"><TeamStatusBadge status={t.status} approval={t.approval_status} /></span>
        </div>
        {t.status === 'PENDING' && (
          <div className="mt-3 rounded-xl bg-navy-700 px-3.5 py-3 text-sm">
            <p className="font-semibold">
              {t.approval_status === 'REJECTED' ? '관리자가 팀 승인을 거절했어요. 문의해 주세요.' : t.approval_status === 'PENDING' ? `관리자 승인을 기다리는 중이에요${need > 0 ? ` · ${need}명 더 필요` : ''}` : `${need}명 더 모이면 일정을 만들 수 있어요`}
            </p>
            <div data-tutorial="INVITE" className="mt-2 flex items-center justify-between gap-2">
              <span className="font-mono text-lg font-black tracking-[0.25em]">{t.team_code}</span>
              <span className="flex gap-1.5">
                <button className="min-h-11 rounded-lg bg-brand px-3 text-xs font-semibold text-on-brand" onClick={() => copyText(t.team_code, '팀 코드를 복사했어요.')}>코드 복사</button>
                <button className="min-h-11 rounded-lg bg-[#FEE500] px-3 text-xs font-semibold text-[#191919]" onClick={() => shareInvite(t.name, t.team_code)}>카카오톡 공유</button>
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-4 border-b border-line bg-surface" role="tablist" aria-label="팀 화면">
        {(['events', 'records', 'tactics', 'members'] as const).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className={`min-h-11 text-sm font-semibold ${tab === k ? 'border-b-2 border-court-500 text-brand-ink' : 'text-faint'}`}>
            {k === 'events' ? '일정' : k === 'records' ? '기록' : k === 'tactics' ? '전술' : `팀원 ${t.member_count}`}
          </button>
        ))}
      </div>

      <Content>
        <GuestClaimCards teamId={id} />
        {myTeamProfile && myTeamProfile.self_rank_level === null && (
          <button onClick={() => nav(`/teams/${id}/self-rank`)} className="flex w-full items-center justify-between rounded-2xl bg-brand px-4 py-3 text-left text-sm font-semibold text-on-brand">
            <span>이 동호회에서 내 실력 위치를 알려 주세요<br /><span className="text-xs font-normal">팀 배정 정확도에 가장 큰 영향을 주는 한 문항이에요</span></span>
            <span>→</span>
          </button>
        )}
        {tab === 'events' ? (
          <>
            {isManager && (
              <Button full variant="secondary" disabled={t.status !== 'ACTIVE'} onClick={() => nav(`/teams/${id}/events/new`)}>
                + 일정 등록{t.status !== 'ACTIVE' ? (t.approval_status !== 'APPROVED' ? ' (관리자 승인 후 가능)' : ` (5명 이상 모이면 가능 · 현재 ${t.member_count}명)`) : ''}
              </Button>
            )}
            {events.isError && !events.data ? (
              // 못 받았는데 "등록된 일정이 없어요" 를 보여 주면 일정이 지워진 줄 안다
              <LoadError message={errMsg(events.error, '일정을 불러오지 못했어요.')} onRetry={() => events.refetch()} retrying={events.isFetching} />
            ) : events.isLoading ? <Spinner /> : sortedEvents.length ? (
              <div className="space-y-2">
                {sortedEvents.length > EVENTS_PAGE && (
                  <div className="flex items-center justify-between text-xs">
                    <button disabled={page === 0} onClick={() => setPage(page - 1)} className="min-h-11 rounded-lg px-3 font-semibold text-ink-2 disabled:opacity-30">‹ 이전</button>
                    <span className="text-center text-muted">{page + 1} / {Math.ceil(sortedEvents.length / EVENTS_PAGE)}{events.hasNextPage ? '+' : ''} · 예정 {upcomingCount}개 · 지난 {sortedEvents.length - upcomingCount}개{events.hasNextPage ? '+' : ''}</span>
                    <button disabled={(page + 1) * EVENTS_PAGE >= sortedEvents.length} onClick={() => setPage(page + 1)} className="min-h-11 rounded-lg px-3 font-semibold text-ink-2 disabled:opacity-30">다음 ›</button>
                  </div>
                )}
                {sortedEvents.slice(page * EVENTS_PAGE, page * EVENTS_PAGE + EVENTS_PAGE).map((e) => (
                  <div key={e.id}>
                    {e.survey_open && e.status !== 'CANCELED' && e.my_attendance === 'ATTEND' && !e.my_survey_submitted && (
                      <button onClick={() => nav(`/events/${e.id}/vote`)} className="mb-1 flex w-full items-center justify-between rounded-2xl bg-brand px-4 py-2.5 text-left text-sm font-semibold text-on-brand">
                        <span>{Number(e.event_date.slice(5, 7))}/{Number(e.event_date.slice(8, 10))} 경기 어땠어요? 같이 뛰고 싶은 사람 뽑기 (30초)</span><span>→</span>
                      </button>
                    )}
                    <EventRow e={e} withDetail={!!e.adopted_candidate_id && e.event_date >= today} past={e.event_date < today} />
                    {e.id === nextAdoptedId && <AdoptedSummary eventId={e.id} isManager={isManager} />}
                  </div>
                ))}
                {/* 마지막 쪽까지 봤는데 서버에 더 오래된 일정이 남아 있으면 다음 묶음을 받는다 */}
                {events.hasNextPage && (page + 1) * EVENTS_PAGE >= sortedEvents.length && (
                  <Button variant="ghost" full loading={events.isFetchingNextPage} onClick={() => events.fetchNextPage().then(() => setPage(page + 1))}>지난 일정 더 불러오기</Button>
                )}
              </div>
            ) : (
              <EmptyState
                title="등록된 일정이 없어요"
                desc={isManager ? (t.status === 'ACTIVE' ? '첫 일정을 등록해 보세요.' : t.approval_status !== 'APPROVED' ? '관리자 승인이 끝나면 일정을 만들 수 있어요.' : `5명 이상 모이면 일정을 만들 수 있어요 (현재 ${t.member_count}명)`) : '매니저가 일정을 올리면 여기에 보여요.'}
              />
            )}
          </>
        ) : tab === 'records' ? (
          <RecordsTab teamId={id} myPlayerId={t.my_player_id} newMonth={newMonth} />
        ) : tab === 'tactics' ? (
          <TacticsTab teamId={id} />
        ) : players.isLoading ? <Spinner /> : (
          <div className="space-y-2">
            {players.isError && !players.data && <LoadError message={errMsg(players.error, '팀원을 불러오지 못했어요.')} onRetry={() => players.refetch()} retrying={players.isFetching} />}
            {players.data?.items.map((p) => <PlayerRow key={p.id} p={p} isMe={p.id === t.my_player_id} />)}
            <LeaveTeamButton teamId={id} teamName={t.name} />
          </div>
        )}
      </Content>
    </Screen>
  )
}

/** 팀 나가기 — 기록은 남고, 팀 코드로 다시 들어올 수 있다. 유일한 매니저는 서버가 거부한다 */
function LeaveTeamButton({ teamId, teamName }: { teamId: number; teamName: string }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [msg, setMsg] = useState<string | null>(null)
  const leave = useMutation({
    mutationFn: () => teamsApi.leave(teamId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['me'] }); qc.invalidateQueries({ queryKey: ['team'] }); qc.invalidateQueries({ queryKey: ['profile'] }); nav('/', { replace: true }) },
    onError: (e) => setMsg(errMsg(e, '나가지 못했어요.')),
  })
  return (
    <div className="pt-2">
      {msg && <Alert>{msg}</Alert>}
      <button
        className="min-h-11 w-full text-center text-xs text-faint underline underline-offset-2" disabled={leave.isPending}
        onClick={async () => { if (await confirm({ title: `'${teamName}' 팀에서 나갈까요?`, body: '기록은 남고, 팀 코드로 다시 들어올 수 있어요.', confirmLabel: '나가기', danger: true })) leave.mutate() }}
      >
        팀 나가기
      </button>
    </div>
  )
}

function PlayerRow({ p, isMe, right, ownerRow }: { p: PlayerCard | PlayerCardDetailed; isMe?: boolean; right?: React.ReactNode; ownerRow?: boolean }) {
  const detailed = 'skill_overall' in p ? p : null  // 매니저 응답(PlayerCardDetailed)에만 등급·수치가 있다
  return (
    <Card className="flex items-center gap-3 py-3">
      <Avatar name={p.display_name} src={p.profile_image_url} />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 truncate font-semibold text-ink">
          {p.display_name}
          {isMe && <span className="text-[11px] font-medium text-brand-ink">(나)</span>}
          {p.kind === 'GUEST' && <Badge>게스트</Badge>}
          {right && p.role === 'MANAGER' && <span className="rounded bg-brand-soft px-1.5 py-0.5 text-[10px] font-semibold text-brand-ink">{ownerRow ? '팀장' : '매니저'}</span>}
        </p>
        <p className="text-xs text-muted">
          {p.playable_positions.length ? p.playable_positions.join(' · ') : '포지션 미입력'}
          {detailed && detailed.skill_overall != null && <span className="ml-2 text-muted">실력 {detailed.skill_overall}</span>}
          {detailed && <span className="ml-2 text-muted">참여 {detailed.attended_events}회</span>}
        </p>
      </div>
      {detailed && <GradeDot grade={p.skill_grade} />}
      <div className="flex shrink-0 justify-end">{right ?? <RoleBadge role={p.role} />}</div>
    </Card>
  )
}

/* ---------- S-08 팀원 관리 (MANAGER) ---------- */
export function MembersPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const nav = useNavigate()
  const team = useQuery({ queryKey: ['team', id], queryFn: () => teamsApi.get(id) })
  const t = team.data
  if (team.isLoading) return <Screen><TopBar title="팀원 관리" back={`/teams/${id}`} /><Spinner /></Screen>
  if (!t) {
    return (
      <Screen>
        <TopBar title="팀원 관리" back={`/teams/${id}`} />
        <Content><LoadError message={errMsg(team.error, '팀을 불러오지 못했어요.')} onRetry={() => team.refetch()} retrying={team.isFetching} /></Content>
      </Screen>
    )
  }
  // 매니저가 아니면 관리 도구를 그리지 않는다 (주소를 직접 쳐서 들어온 경우)
  if (t.my_role !== 'MANAGER') {
    return (
      <Screen>
        <TopBar title="팀원 관리" back={`/teams/${id}`} />
        <Content>
          <Alert>매니저만 볼 수 있는 화면이에요.</Alert>
          <Button variant="secondary" full onClick={() => nav(`/teams/${id}`, { replace: true })}>팀 화면으로</Button>
        </Content>
      </Screen>
    )
  }
  return <MembersManager team={t} />
}

function MembersManager({ team: t }: { team: TeamDetail }) {
  const id = t.id
  const nav = useNavigate()
  const qc = useQueryClient()
  const players = useQuery({ queryKey: ['team', id, 'players', 'skill'], queryFn: () => teamsApi.players(id, 'skill') })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['team', id] }); qc.invalidateQueries({ queryKey: ['me', 'teams'] }) }  // 'team', id 프리픽스로 players·merge-candidates 도 함께 갱신

  const me = useMe()
  const [open, setOpen] = useState<number | null>(null)  // 관리 메뉴가 펼쳐진 회원
  // 결과 알림은 모두 토스트로 — 목록 아래쪽에서 누르면 화면 위 Alert 는 보이지 않는다
  const setRole = useMutation({
    mutationFn: ({ pid, role }: { pid: number; role: 'MANAGER' | 'PLAYER' }) => teamsApi.setRole(id, pid, role),
    onSuccess: (_, v) => {
      refresh(); setOpen(null)
      toast(v.role === 'MANAGER' ? '매니저로 지정했어요.' : '매니저 권한을 해제했어요.')
      if (v.pid === t.my_player_id && v.role === 'PLAYER') nav(`/teams/${id}`, { replace: true })  // 본인 해제 → 이 화면을 볼 수 없다
    },
    onError: (e) => toast(errMsg(e, '권한을 바꾸지 못했어요.'), 'error'),
  })
  const isOwner = !!me.data && t.owner.id === me.data.id  // 팀장 = 팀을 만든 사람. 권한 부여·회수 · 매니저 제외는 팀장만
  const changeRole = async (p: PlayerCard, isMe: boolean, managers: PlayerCard[]) => {
    const demote = p.role === 'MANAGER'
    if (demote) {
      const others = managers.filter((m) => m.id !== p.id)
      if (others.length === 0) { toast('매니저가 1명뿐이라 해제할 수 없어요. 먼저 다른 팀원을 매니저로 지정해 주세요.', 'error'); return }
      if (isMe) {
        const next = [...others].sort((a, b) => a.id - b.id)[0]  // 서버와 같은 규칙: 가장 먼저 매니저가 된 사람
        const ok = await confirm({
          title: '내 매니저 권한을 해제할까요?',
          body: `팀장 권한이 ${next.display_name}님에게 넘어가고, 이 팀 관리 화면에 더 이상 들어올 수 없어요. 되돌리려면 ${next.display_name}님이 다시 지정해 줘야 해요.`,
          confirmLabel: '해제하기', danger: true,
        })
        if (!ok) return
      }
    }
    setRole.mutate({ pid: p.id, role: demote ? 'PLAYER' : 'MANAGER' })
  }
  const [editTeam, setEditTeam] = useState(false)
  const [tf, setTf] = useState({ name: '', description: '', home_court: '' })
  const saveTeam = useMutation({
    mutationFn: () => teamsApi.update(id, { name: tf.name.trim(), description: tf.description.trim() || undefined, home_court: tf.home_court.trim() || undefined }),
    onSuccess: () => { toast('팀 정보를 저장했어요.'); setEditTeam(false); refresh() },
    meta: { inlineError: true },
  })
  const remove = useMutation({
    mutationFn: (pid: number) => teamsApi.remove(id, pid),
    onSuccess: () => { toast('팀에서 제외했어요.'); setOpen(null); refresh() },
    onError: (e) => toast(errMsg(e, '제외하지 못했어요.'), 'error'),
  })
  const regen = useMutation({
    mutationFn: () => teamsApi.regenerateCode(id),
    onSuccess: (r) => { toast(`새 팀 코드: ${r.team_code}`); refresh() },
    onError: (e) => toast(errMsg(e, '코드를 다시 만들지 못했어요.'), 'error'),
  })
  const candidates = useQuery({ queryKey: ['team', id, 'merge-candidates'], queryFn: () => teamsApi.mergeCandidates(id) })
  const merge = useMutation({
    mutationFn: ({ guest, into }: { guest: number; into: number }) => teamsApi.mergeGuest(guest, into),
    onSuccess: () => { toast('병합했어요. 게스트 기록이 회원 계정으로 이어졌어요.'); refresh(); qc.invalidateQueries({ queryKey: ['stats'] }) },
    onError: (e) => toast(errMsg(e, '병합하지 못했어요.'), 'error'),
  })

  type SortKey = 'position' | 'skill' | 'attendance'
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'skill', desc: true })
  const clickSort = (key: SortKey) => setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: true }))  // 같은 버튼 다시 누르면 방향 반전
  const POS_ORDER: Record<string, number> = { PG: 0, SG: 1, SF: 2, PF: 3, C: 4 }
  const members = [...(players.data?.items.filter((p) => p.kind === 'MEMBER') ?? [])].sort((a, b) => {
    const da = a as PlayerCardDetailed, db = b as PlayerCardDetailed
    let cmp = 0
    if (sort.key === 'position') {
      const pa = a.primary_position ? POS_ORDER[a.primary_position] : 9, pb = b.primary_position ? POS_ORDER[b.primary_position] : 9
      cmp = pb - pa  // 내림차순 = C → PG. 뒤집으면 PG → C
    } else if (sort.key === 'attendance') {
      cmp = (da.attended_events ?? 0) - (db.attended_events ?? 0)
    } else {
      const sa = da.skill_overall ?? da.prior_overall, sb = db.skill_overall ?? db.prior_overall
      cmp = (sa === null ? -1e9 : Number(sa)) - (sb === null ? -1e9 : Number(sb))
    }
    if (sort.desc) cmp = -cmp
    return cmp || a.display_name.localeCompare(b.display_name)
  })

  return (
    <Screen>
      <TopBar title="팀원 관리" back={`/teams/${id}`} />
      <Content>
        {editTeam ? (
          <Card className="space-y-3">
            <Field label="팀 이름" value={tf.name} onChange={(e) => setTf({ ...tf, name: e.target.value })} maxLength={50} required />
            <Field label="팀 소개 (선택)" value={tf.description} onChange={(e) => setTf({ ...tf, description: e.target.value })} placeholder="매주 일요일 오전, 게스트 환영" />
            <Field label="홈 코트 (선택)" value={tf.home_court} onChange={(e) => setTf({ ...tf, home_court: e.target.value })} maxLength={100} />
            {saveTeam.isError && <Alert>{errMsg(saveTeam.error, '저장하지 못했어요.')}</Alert>}
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setEditTeam(false)}>취소</Button>
              <Button full loading={saveTeam.isPending} disabled={!tf.name.trim()} onClick={() => saveTeam.mutate()}>저장</Button>
            </div>
          </Card>
        ) : (
          <Card className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-bold text-ink">{t.name}</p>
              <p className="truncate text-xs text-muted">{t.description || '팀 소개가 없어요'}{t.home_court ? ` · ${t.home_court}` : ''}</p>
            </div>
            <Button variant="ghost" className="text-sm" onClick={() => { setTf({ name: t.name, description: t.description ?? '', home_court: t.home_court ?? '' }); saveTeam.reset(); setEditTeam(true) }}>수정</Button>
          </Card>
        )}
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted">팀 코드</p>
            <p className="font-mono text-xl font-black tracking-[0.25em] text-ink">{t.team_code}</p>
          </div>
          <Button
            variant="ghost" className="shrink-0 text-sm" loading={regen.isPending}
            onClick={async () => { if (await confirm({ title: '팀 코드를 다시 만들까요?', body: '기존 코드와 이미 보낸 초대 링크는 더 이상 쓸 수 없어요.', confirmLabel: '재발급' })) regen.mutate() }}
          >
            재발급
          </Button>
        </Card>
        <Card className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">팀원 초대하기</p>
            <p className="text-xs text-muted">링크를 받은 사람은 코드 입력 없이 바로 가입해요.</p>
          </div>
          <button
            className="min-h-11 shrink-0 whitespace-nowrap rounded-xl bg-[#FEE500] px-3 text-sm font-semibold text-[#191919] active:brightness-95"
            onClick={() => shareInvite(t.name, t.team_code)}
          >
            카카오톡 초대
          </button>
        </Card>
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted">실력 정렬</p>
            <p className="text-sm font-semibold text-ink">팀원 순서를 매기면 처음 실력에 반영돼요</p>
          </div>
          <Button variant="ghost" className="text-sm" onClick={() => nav(`/teams/${id}/ranking`)}>정렬하기</Button>
        </Card>
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted">지난 기록 추가</p>
            <p className="text-sm font-semibold text-ink">앱을 쓰기 전 경기 기록 남기기</p>
          </div>
          <Button variant="ghost" className="text-sm" onClick={() => nav(`/teams/${id}/records/new`)}>추가하기</Button>
        </Card>

        <section>
          <SectionTitle action={
            <div className="-my-2 flex">
              {([['skill', '실력'], ['position', '포지션'], ['attendance', '참여']] as const).map(([k, l]) => {
                const on = sort.key === k
                const hint = !on ? '' : k === 'position' ? (sort.desc ? ' C→PG' : ' PG→C') : sort.desc ? ' 높은순' : ' 낮은순'
                return (
                  // 보이는 칩은 작게, 누르는 칸은 44px
                  <button key={k} onClick={() => clickSort(k)} aria-pressed={on} className="flex min-h-11 items-center px-0.5">
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${on ? 'bg-navy-800 text-white' : 'bg-sunken text-muted'}`}>
                      {l}{hint}{on ? (sort.desc ? ' ▼' : ' ▲') : ''}
                    </span>
                  </button>
                )
              })}
            </div>
          }>팀원 {members.length}</SectionTitle>
          {players.isError && !players.data ? (
            <LoadError message={errMsg(players.error, '팀원을 불러오지 못했어요.')} onRetry={() => players.refetch()} retrying={players.isFetching} />
          ) : players.isLoading ? <Spinner /> : (
            <div className="space-y-2">
              {members.map((p) => {
                const isMe = p.id === t.my_player_id
                const menu = open === p.id
                const ownerRow = p.user_id === t.owner.id
                const managers = members.filter((m) => m.role === 'MANAGER')
                // 팀장은 아무도 제외할 수 없고, 매니저는 팀장만 제외할 수 있다 (서버도 403 으로 막는다)
                const removeBlock = isMe ? '본인 제외 불가' : ownerRow ? '팀장 제외 불가' : p.role === 'MANAGER' && !isOwner ? '매니저는 팀장만 제외' : null
                return (
                  <div key={p.id}>
                    <PlayerRow
                      p={p}
                      isMe={isMe}
                      ownerRow={ownerRow}
                      right={
                        <button aria-label={`${p.display_name} 관리`} aria-expanded={menu} className={`-my-1 flex size-11 items-center justify-center rounded-lg text-lg font-bold ${menu ? 'bg-navy-800 text-white' : 'bg-sunken text-ink-2'}`} onClick={() => setOpen(menu ? null : p.id)}>⋯</button>
                      }
                    />
                    {menu && (
                      <div className="-mt-1 grid grid-cols-3 gap-2 rounded-b-2xl border border-t-0 border-line bg-surface-2 px-3 py-2">
                        <button className="min-h-11 rounded-xl bg-surface text-xs font-semibold text-ink shadow-sm active:bg-sunken" onClick={() => nav(`/teams/${id}/players/${p.id}`)}>실력 보기</button>
                        {isOwner ? (
                          <button className="min-h-11 rounded-xl bg-surface text-xs font-semibold text-ink shadow-sm active:bg-sunken disabled:opacity-50" disabled={setRole.isPending} onClick={() => changeRole(p, isMe, managers)}>{p.role === 'MANAGER' ? '매니저 해제' : '매니저 지정'}</button>
                        ) : (
                          <button className="min-h-11 rounded-xl bg-surface text-xs font-semibold text-faint shadow-sm" onClick={() => toast('매니저 지정·해제는 팀장(팀을 만든 사람)만 할 수 있어요.')}>팀장 전용</button>
                        )}
                        <button
                          className="min-h-11 rounded-xl bg-surface px-1 text-xs font-semibold text-danger-ink shadow-sm active:bg-danger-soft disabled:text-faint disabled:opacity-60"
                          disabled={!!removeBlock || remove.isPending}
                          onClick={async () => { if (await confirm({ title: `${p.display_name}님을 팀에서 제외할까요?`, body: '경기 기록은 남아요. 다시 들어오려면 팀 코드로 가입 요청을 해야 해요.', confirmLabel: '제외하기', danger: true })) remove.mutate(p.id) }}
                        >
                          {removeBlock ?? '팀에서 제외'}
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {candidates.data && candidates.data.items.length > 0 && (
          <section>
            <SectionTitle>기록 이어받기 제안</SectionTitle>
            <Alert kind="info">같은 이름의 게스트 기록이 있어요. 같은 사람이면 병합해 기록을 이어 주세요. 동명이인일 수 있으니 확인 후 눌러 주세요.</Alert>
            <div className="mt-2 space-y-2">
              {candidates.data.items.map((c) => (
                <Card key={`${c.guest.id}-${c.member.id}`} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-semibold text-ink">게스트 {c.guest.display_name} <span className="text-faint">→</span> 팀원 {c.member.display_name}</p>
                    <p className="text-xs text-muted">게스트 기록(배정·쿼터·투표)이 회원 계정으로 승계돼요. 되돌릴 수 있어요.</p>
                  </div>
                  {/* 누른 줄에만 도는 표시 — 다른 줄은 잠깐 누를 수 없게만 */}
                  <Button
                    className="text-sm" disabled={merge.isPending} loading={merge.isPending && merge.variables?.guest === c.guest.id}
                    onClick={async () => { if (await confirm({ title: '기록을 병합할까요?', body: `게스트 ${c.guest.display_name}의 기록을 ${c.member.display_name}님에게 이어 붙여요.`, confirmLabel: '병합' })) merge.mutate({ guest: c.guest.id, into: c.member.id }) }}
                  >
                    병합
                  </Button>
                </Card>
              ))}
            </div>
          </section>
        )}

      </Content>
    </Screen>
  )
}
