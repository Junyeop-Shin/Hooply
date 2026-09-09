/** S-04 홈 (역할별) · S-17 내 프로필 · 내 팀 목록. */
import { useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { eventsApi } from '../api/events'
import { peerApi } from '../api/peer'
import { MarginTrend, QuarterList } from './player-detail'
import { surveyApi } from '../api/survey'
import { POSITIONS, SELF_RANK_LABEL, localISODate, type EventView, type Position } from '../api/types'
import { useAuthStore } from '../store/auth'
import { Avatar, Badge, Button, Card, EmptyState, RoleBadge, SectionTitle, Spinner, TeamStatusBadge } from '../components/ui'
import { Content, Screen, TabBar, TopBar } from '../components/layout'
import { fmtEvent } from './events'

export function useMe() {
  return useQuery({ queryKey: ['me'], queryFn: authApi.me })
}
export function useMyTeams() {
  return useQuery({ queryKey: ['me', 'teams'], queryFn: authApi.myTeams })
}

/** 내 모든 팀의 아직 진행하지 않은 일정 (가까운 순). 지난 일정은 팀 화면 일정 탭에서 본다 */
function useUpcoming(teamIds: number[]) {
  const results = useQueries({
    queries: teamIds.map((id) => ({ queryKey: ['events', 'team', id, 'all', 50], queryFn: () => eventsApi.list(id, { size: 50 }) })),
  })
  const today = localISODate()
  const upcoming: EventView[] = results
    .flatMap((r) => r.data?.items ?? [])
    .filter((e) => e.status !== 'CANCELED' && e.event_date >= today)
    .sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  return { upcoming, isLoading: results.some((r) => r.isLoading) }
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

  return (
    <Screen>
      <TopBar tone="navy" title={<span className="flex items-center gap-2"><span className="flex size-6 items-center justify-center rounded-md bg-court-500 text-[12px] font-black text-white">H</span><span className="tracking-[0.12em]">HOOPLY</span></span>} />
      <Content>
        <div className="rounded-2xl bg-navy-800 p-5 text-white">
          <p className="text-sm text-navy-200">안녕하세요,</p>
          <p className="text-xl font-bold">{me.data ? `${me.data.nickname ?? me.data.name}님` : '…'}</p>
          {me.data && !me.data.onboarding_completed ? (
            <Link to="/survey" className="mt-3 flex items-center justify-between rounded-xl bg-court-500 px-4 py-3 text-sm font-semibold">
              실력 설문을 아직 안 하셨어요 · 2분이면 끝나요 <span>→</span>
            </Link>
          ) : next ? (
            <Link to={`/events/${next.id}`} state={{ from: '/' }} className="mt-3 flex items-center justify-between rounded-xl bg-navy-700 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[11px] text-navy-200">다음 모임 {dday(next.event_date)}{nameOf(next.team_id) ? ` · ${nameOf(next.team_id)}` : ''}</p>
                <p className="truncate text-sm font-bold">{fmtEvent(next)}{next.venue ? ` · ${next.venue}` : ''}</p>
              </div>
              <span className={`ml-2 shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${next.my_attendance === 'ATTEND' ? 'bg-court-500' : next.my_attendance === 'ABSENT' ? 'bg-white/10 text-navy-200' : 'bg-amber-400 text-navy-900'}`}>
                {next.my_attendance === 'ATTEND' ? '참석' : next.my_attendance === 'ABSENT' ? '불참' : '응답하기'}
              </span>
            </Link>
          ) : null}
        </div>

        <section>
          <SectionTitle>다가오는 일정</SectionTitle>
          {upcoming.isLoading ? <Spinner /> : upcoming.upcoming.length ? (
            <div className="space-y-2">
              {upcoming.upcoming.map((e) => <EventRow key={e.id} e={e} teamName={nameOf(e.team_id)} />)}
            </div>
          ) : (
            <EmptyState title="예정된 일정이 없어요" desc={isManagerSomewhere ? '팀 상세에서 일정을 등록해 보세요.' : '매니저가 일정을 올리면 여기에 보여요.'} />
          )}
        </section>

        <section>
          <SectionTitle>내 팀</SectionTitle>
          {teams.isLoading ? <Spinner /> : teamList.length ? (
            <div className="space-y-2">
              {teamList.map((t) => <TeamRow key={t.team_id} {...t} primary={teamList.length > 1 ? (me.data?.primary_team_id ?? teamList[0].team_id) === t.team_id : null} />)}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Link to="/teams/join" className="flex min-h-11 items-center justify-center rounded-xl border border-dashed border-stone-300 bg-white/60 text-sm font-semibold text-navy-700">+ 팀 코드로 가입</Link>
                <Link to="/teams/new" className="flex min-h-11 items-center justify-center rounded-xl border border-dashed border-stone-300 bg-white/60 text-sm font-semibold text-navy-700">+ 팀 만들기</Link>
              </div>
            </div>
          ) : (
            <EmptyState title="아직 소속된 팀이 없어요" desc="팀 코드를 받았다면 가입하고, 없다면 직접 만들어 보세요."
              action={<div className="flex gap-2"><Link to="/teams/join"><Button variant="secondary">코드로 가입</Button></Link><Link to="/teams/new"><Button>팀 만들기</Button></Link></div>}
            />
          )}
        </section>
      </Content>
      <TabBar />
    </Screen>
  )
}

export function EventRow({ e, teamName, withDetail, past }: { e: EventView; teamName?: string; withDetail?: boolean; past?: boolean }) {
  const nav = useNavigate()
  const my = e.my_attendance
  return (
    <Card onClick={() => nav(`/events/${e.id}`, { state: { from: window.location.pathname } })} className={`flex items-center gap-3 ${withDetail ? 'rounded-b-none' : ''} ${past ? 'opacity-75' : ''}`}>
      <div className={`flex size-12 flex-col items-center justify-center rounded-xl ${past ? 'bg-stone-100 text-stone-500' : 'bg-navy-50 text-navy-800'}`}>
        <span className="text-[10px] leading-none">{Number(e.event_date.slice(5, 7))}월</span>
        <span className="text-lg font-black leading-tight">{Number(e.event_date.slice(8, 10))}</span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-bold text-navy-900">{e.title ?? fmtEvent(e)}</p>
        <p className="truncate text-xs text-stone-500">{teamName ? `${teamName} · ` : ''}{fmtEvent(e)}{e.venue ? ` · ${e.venue}` : ''}</p>
        {e.my_squad_name && !withDetail && <p className="text-xs font-semibold text-court-600">배정 확정 · {e.my_squad_name}{e.my_assigned_position ? ` ${e.my_assigned_position}` : ''}</p>}
      </div>
      <div className="flex flex-col items-end gap-1">
        {e.status === 'CANCELED' ? <Badge>취소됨</Badge> : my === 'ATTEND' ? <Badge tone="success">참석</Badge> : my === 'ABSENT' ? <Badge>불참</Badge> : <Badge tone="warn">미응답</Badge>}
        <span className="text-[11px] text-stone-500">참석 {e.attend_count}</span>
      </div>
    </Card>
  )
}

/** 팀 카드. 팀이 둘 이상이면 "기본" 표시와 "기본 팀으로 설정하기" 버튼 — 목록 맨 위·프로필이 먼저 보여줄 팀 */
function TeamRow(t: { team_id: number; team_name: string; team_status: 'PENDING' | 'ACTIVE' | 'ARCHIVED'; approval_status: 'PENDING' | 'APPROVED' | 'REJECTED'; role: 'MANAGER' | 'PLAYER'; member_count: number; primary: boolean | null }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const setPrimary = useMutation({
    mutationFn: () => authApi.updateMe({ primary_team_id: t.team_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['me'] }),
  })
  return (
    <Card onClick={() => nav(`/teams/${t.team_id}`)} className="flex items-center gap-3">
      <span className="flex size-11 items-center justify-center rounded-xl bg-court-50 text-base font-black text-court-600">{t.team_name.slice(0, 1)}</span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 truncate font-bold text-navy-900">{t.team_name}{t.primary && <Badge tone="court">기본</Badge>}</p>
        <p className="text-xs text-stone-500">
          회원 {t.member_count}명
          {t.primary === false && (
            <> · <button onClick={(e) => { e.stopPropagation(); setPrimary.mutate() }} disabled={setPrimary.isPending} className="text-xs text-stone-500 underline underline-offset-2">기본 팀으로 설정하기</button></>
          )}
        </p>
      </div>
      <div className="flex flex-col items-end gap-1"><RoleBadge role={t.role} /><TeamStatusBadge status={t.team_status} approval={t.approval_status} /></div>
    </Card>
  )
}

export function ProfilePage() {
  const me = useMe()
  const profile = useQuery({ queryKey: ['profile'], queryFn: surveyApi.myProfile })
  const logout = useAuthStore((s) => s.logout)
  const nav = useNavigate()
  const u = me.data
  const p = profile.data
  const [chosen, setChosen] = useState<number | null>(null)
  const teams = [...(p?.teams ?? [])].sort((a, b) => Number(b.team_id === u?.primary_team_id) - Number(a.team_id === u?.primary_team_id))  // 기본 팀이 가장 왼쪽
  const current = teams.find((t) => t.team_id === (chosen ?? u?.primary_team_id)) ?? teams[0]
  return (
    <Screen>
      <TopBar title="내 프로필" />
      <Content>
        {!u ? <Spinner /> : (
          <>
            <Card className="flex items-center gap-4">
              <Avatar name={u.nickname ?? u.name} size="lg" />
              <div className="min-w-0 flex-1">
                <p className="text-lg font-bold text-navy-900">{u.nickname ?? u.name}</p>
                <p className="truncate text-sm text-stone-500">{u.email ?? '이메일 없음 (카카오 계정)'}</p>
                <div className="mt-1.5 flex gap-1.5">
                  {u.identities.map((i) => <Badge key={i.provider} tone={i.provider === 'KAKAO' ? 'warn' : 'navy'}>{i.provider === 'KAKAO' ? '카카오' : '이메일'}</Badge>)}
                  {u.global_role === 'ADMIN' && <Badge tone="court">관리자</Badge>}
                  {u.height_cm && <Badge>{u.height_cm}cm</Badge>}
                </div>
              </div>
            </Card>

            <section>
              <SectionTitle>포지션</SectionTitle>
              {u.onboarding_completed && p ? (
                <PositionEditor key={p.playable_positions.join(',')} current={p.playable_positions} />
              ) : (
                <Card className="flex items-center justify-between gap-3">
                  <div><p className="font-semibold text-navy-900">설문을 완료해 주세요</p><p className="text-xs text-stone-500">실력·포지션 프로필이 아직 없어요.</p></div>
                  <Button onClick={() => nav('/survey')}>설문하기</Button>
                </Card>
              )}
            </section>

            {teams.length > 1 && (
              <div className="flex gap-1.5 overflow-x-auto px-1">
                {teams.map((t) => (
                  <button key={t.team_id} onClick={() => setChosen(t.team_id)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${current?.team_id === t.team_id ? 'bg-navy-800 text-white' : 'bg-stone-100 text-stone-500'}`}>
                    {t.team_name}{u?.primary_team_id === t.team_id ? ' (기본)' : ''}
                  </button>
                ))}
              </div>
            )}

            {current && (
              <section>
                <SectionTitle>{teams.length > 1 ? `${current.team_name} 설정` : '팀별 설정'}</SectionTitle>
                <Card className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-stone-500">이 동호회에서 내 실력 위치</p>
                    {current.self_rank_level ? (
                      <p className="mt-0.5"><Badge tone="court">{SELF_RANK_LABEL[current.self_rank_level]}</Badge></p>
                    ) : (
                      <p className="mt-0.5 text-sm font-semibold text-court-600">아직 안 알려줬어요 — 배정 정확도에 가장 큰 영향을 줘요</p>
                    )}
                  </div>
                  <Button variant="ghost" className="min-h-10 text-sm" onClick={() => nav(`/teams/${current.team_id}/self-rank`)}>{current.self_rank_level ? '수정' : '설정'}</Button>
                </Card>
              </section>
            )}

            {current ? (
              <RecordsSection key={current.team_id} teamName={current.team_name} playerId={current.player_id} many={false} />
            ) : (
              <section>
                <SectionTitle>기록</SectionTitle>
                <EmptyState title="아직 경기 기록이 없어요" desc="팀에 가입하고 쿼터 기록이 쌓이면 여기에 나와요." />
              </section>
            )}

            <Button variant="danger" full onClick={() => { logout(); nav('/login', { replace: true }) }}>로그아웃</Button>
          </>
        )}
      </Content>
      <TabBar />
    </Screen>
  )
}

/** 가능 포지션을 선호 순서대로 고르는 편집기. 첫 번째가 가장 선호. 저장하면 소속 팀 전부에 반영된다. */
function PositionEditor({ current }: { current: Position[] }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [order, setOrder] = useState<Position[]>(current)
  const save = useMutation({
    mutationFn: () => surveyApi.updatePositions(order.map((position) => ({ position }))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['team'] }); setEditing(false) },
  })
  if (!editing) {
    return (
      <Card className="flex items-center gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {current.length === 0 && <span className="text-sm text-stone-500">포지션 정보 없음</span>}
          {current.map((pos, i) => <Badge key={pos} tone={i === 0 ? 'court' : 'navy'}>{i === 0 ? `${pos} 선호` : pos}</Badge>)}
        </div>
        <Button variant="ghost" className="min-h-10 text-sm" onClick={() => { setOrder(current); setEditing(true) }}>수정</Button>
      </Card>
    )
  }
  return (
    <Card className="space-y-3">
      <p className="text-sm text-stone-600">할 수 있는 포지션을 <b>선호하는 순서대로</b> 눌러 주세요. 다시 누르면 빠져요.</p>
      <div className="flex gap-1.5">
        {POSITIONS.map((pos) => {
          const idx = order.indexOf(pos)
          return (
            <button key={pos} type="button" onClick={() => setOrder(idx >= 0 ? order.filter((x) => x !== pos) : [...order, pos])}
              className={`relative min-h-11 flex-1 rounded-lg border text-sm font-bold ${idx >= 0 ? 'border-court-500 bg-court-500 text-white' : 'border-stone-200 bg-white text-navy-800'}`}>
              {idx >= 0 && <span className="absolute -left-1 -top-1.5 flex size-5 items-center justify-center rounded-full bg-navy-800 text-[11px] text-white">{idx + 1}</span>}
              {pos}
            </button>
          )
        })}
      </div>
      <div className="flex gap-2">
        <Button variant="ghost" onClick={() => setEditing(false)}>취소</Button>
        <Button full loading={save.isPending} disabled={order.length === 0} onClick={() => save.mutate()}>저장</Button>
      </div>
    </Card>
  )
}

/** S-17 기록 — 참여 회차·출전 쿼터·회차별 마진·내가 뛴 쿼터. 실력 수치·등급은 본인에게 보이지 않는다 (FR-28). */
function RecordsSection({ teamName, playerId, many }: { teamName: string; playerId: number; many: boolean }) {
  const q = useQuery({ queryKey: ['stats', playerId], queryFn: () => peerApi.stats(playerId) })
  const s = q.data
  return (
    <section>
      <SectionTitle>기록{many ? ` · ${teamName}` : ''}</SectionTitle>
      {q.isLoading || !s ? <Spinner /> : s.quarters_played === 0 ? (
        <EmptyState title="아직 경기 기록이 없어요" desc={`참석 ${s.events_attended}회 · 매니저가 쿼터를 기록하면 여기에 나와요.`} />
      ) : (
        <div className="space-y-2">
          <Card className="grid grid-cols-3 text-center">
            <div><p className="text-2xl font-black text-navy-900">{s.events_attended}</p><p className="text-[11px] text-stone-500">참석 회차</p></div>
            <div><p className="text-2xl font-black text-navy-900">{s.quarters_played}</p><p className="text-[11px] text-stone-500">출전 쿼터</p></div>
            <div><p className="text-2xl font-black text-court-600">{s.margin_trend.reduce((a, m) => a + m.wins, 0)}<span className="text-sm text-stone-400">/{s.quarters_played}</span></p><p className="text-[11px] text-stone-500">이긴 쿼터</p></div>
          </Card>
          <MarginTrend points={s.margin_trend} />
          <QuarterList records={s.recent_quarters} />
        </div>
      )}
    </section>
  )
}

/** D-day 표기: 오늘 = D-DAY, 내일 = D-1 */
function dday(date: string) {
  const diff = Math.round((new Date(date + 'T00:00:00').getTime() - new Date(new Date().toDateString()).getTime()) / 86_400_000)
  return diff <= 0 ? 'D-DAY' : `D-${diff}`
}
