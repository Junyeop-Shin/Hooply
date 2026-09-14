/** S-05 팀 생성 · S-06 팀 가입 · S-07 팀 상세 · S-08 팀원 관리 (FR-04 ~ FR-07). */
import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { teamsApi } from '../api/teams'
import { eventsApi } from '../api/events'
import { EventRow, GuestClaimCards, useMe } from './home'
import { fmtEvent } from '../lib/format'
import { SHARE_DONE, shareText } from '../lib/kakao'
import { AdoptedSummary } from './assignment'
import { surveyApi } from '../api/survey'
import { localISODate, type PlayerCard, type PlayerCardDetailed } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, EmptyState, Field, GradeDot, RoleBadge, SectionTitle, Spinner, TeamStatusBadge } from '../components/ui'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)
const EVENTS_PAGE = 5

/* ---------- S-05 팀 생성 ---------- */
export function TeamCreatePage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', description: '', home_court: '' })
  const [created, setCreated] = useState<{ id: number; team_code: string } | null>(null)
  const m = useMutation({
    mutationFn: () => teamsApi.create({ name: form.name, description: form.description || undefined, home_court: form.home_court || undefined }),
    onSuccess: (res) => { setCreated(res); qc.invalidateQueries({ queryKey: ['me', 'teams'] }) },
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
          <Field label="팀 이름" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="화요농구" maxLength={50} required />
          <Field label="소개 (선택)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="매주 화요일 8시, 초보 환영" />
          <Field label="홈 코트 (선택)" value={form.home_court} onChange={(e) => setForm({ ...form, home_court: e.target.value })} placeholder="서초체육관" maxLength={100} />
          {m.isError && <Alert>{errMsg(m.error, '팀을 만들지 못했어요.')}</Alert>}
          <Alert kind="info">팀을 만든 사람이 매니저가 돼요. 나중에 다른 팀원에게 권한을 넘길 수 있어요.</Alert>
        </Content>
        <BottomAction><Button type="submit" full loading={m.isPending}>팀 코드 발급받기</Button></BottomAction>
      </form>
    </Screen>
  )
}

/** 팀 코드 공유 문구 + 가입 링크 (S-06 이 ?code= 로 코드를 미리 채운다) */
export const teamInviteText = (name: string, code: string) => ({
  text: `[HOOPLY] ${name} 팀에 초대해요.\n팀 코드 ${code} 를 넣고 가입해 주세요.`,
  url: `${window.location.origin}/teams/join?code=${code}`,
})

function TeamCodeBox({ code, teamName }: { code: string; teamName: string }) {
  const [msg, setMsg] = useState<string | null>(null)
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setMsg('복사했어요.'); setTimeout(() => setMsg(null), 1500) } catch { /* 클립보드 미지원 */ }
  }
  const share = async () => { const { text, url } = teamInviteText(teamName, code); setMsg(SHARE_DONE[await shareText(text, url)]) }
  return (
    <div className="mt-2 w-full rounded-2xl border-2 border-dashed border-court-300 bg-brand-soft p-4">
      <p className="text-xs font-semibold text-brand-ink">팀 코드</p>
      <p className="my-1 font-mono text-3xl font-black tracking-[0.3em] text-ink">{code}</p>
      <div className="flex justify-center gap-2">
        <Button variant="secondary" onClick={copy} className="min-h-10 text-sm">복사</Button>
        <button onClick={share} className="min-h-10 rounded-xl bg-[#FEE500] px-4 text-sm font-semibold text-[#191919] active:brightness-95">카카오톡 공유</button>
      </div>
      {msg && <p className="mt-2 text-xs text-brand-ink">{msg}</p>}
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
  })
  const err = m.error instanceof ApiError ? m.error : null
  return (
    <Screen>
      <TopBar title="팀 코드로 가입" back="/" />
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate() }} className="flex flex-1 flex-col">
        <Content>
          <Field
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
          />
          {err && err.code !== 'TEAM_CODE_NOT_FOUND' && (
            <Alert kind={err.code === 'ALREADY_MEMBER' ? 'info' : 'error'}>{err.message}</Alert>
          )}
        </Content>
        <BottomAction><Button type="submit" full loading={m.isPending} disabled={code.length !== 8}>가입하기</Button></BottomAction>
      </form>
    </Screen>
  )
}

/* ---------- S-07 팀 상세 ---------- */
export function TeamDetailPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const nav = useNavigate()
  const [tab, setTab] = useState<'events' | 'members'>('events')
  const team = useQuery({ queryKey: ['team', id], queryFn: () => teamsApi.get(id) })
  const players = useQuery({ queryKey: ['team', id, 'players'], queryFn: () => teamsApi.players(id), enabled: tab === 'members' })
  const events = useQuery({ queryKey: ['events', 'team', id, 'all', 50], queryFn: () => eventsApi.list(id, { size: 50 }), enabled: tab === 'events' })
  const profile = useQuery({ queryKey: ['profile'], queryFn: surveyApi.myProfile })
  const myTeamProfile = profile.data?.teams.find((t) => t.team_id === id)
  const today = localISODate()
  const [page, setPage] = useState(0)
  // 아직 진행하지 않은 일정(가까운 순)이 먼저, 그 뒤에 지난 일정(최근 순). 5개씩 페이지
  const all = (events.data?.items ?? []).filter((e) => e.status !== 'CANCELED')
  const upcomingList = all.filter((e) => e.event_date >= today).sort((a, b) => a.event_date.localeCompare(b.event_date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  const pastList = all.filter((e) => e.event_date < today).sort((a, b) => b.event_date.localeCompare(a.event_date))
  const sortedEvents = [...upcomingList, ...pastList]
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
      <TopBar tone="navy" title={t.name} back="/" right={isManager && <Link to={`/teams/${id}/members`} className="mr-1 text-sm font-semibold text-court-300">팀 관리</Link>} />
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
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="font-mono text-lg font-black tracking-[0.25em]">{t.team_code}</span>
              <span className="flex gap-1.5">
                <button className="rounded-lg bg-court-500 px-3 py-1.5 text-xs font-semibold" onClick={() => navigator.clipboard?.writeText(t.team_code)}>코드 복사</button>
                <button className="rounded-lg bg-[#FEE500] px-3 py-1.5 text-xs font-semibold text-[#191919]" onClick={async () => { const { text, url } = teamInviteText(t.name, t.team_code); const r = SHARE_DONE[await shareText(text, url)]; if (r) alert(r) }}>카카오톡 공유</button>
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 border-b border-line bg-surface">
        {(['events', 'members'] as const).map((k) => (
          <button key={k} onClick={() => setTab(k)} className={`min-h-11 text-sm font-semibold ${tab === k ? 'border-b-2 border-court-500 text-brand-ink' : 'text-faint'}`}>
            {k === 'events' ? '일정' : `팀원 ${t.member_count}`}
          </button>
        ))}
      </div>

      <Content>
        <GuestClaimCards teamId={id} />
        {myTeamProfile && myTeamProfile.self_rank_level === null && (
          <button onClick={() => nav(`/teams/${id}/self-rank`)} className="flex w-full items-center justify-between rounded-2xl bg-court-500 px-4 py-3 text-left text-sm font-semibold text-white">
            <span>이 동호회에서 내 실력 위치를 알려 주세요<br /><span className="text-[11px] font-normal text-court-100">팀 배정 정확도에 가장 큰 영향을 주는 한 문항이에요</span></span>
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
            {events.isLoading ? <Spinner /> : sortedEvents.length ? (
              <div className="space-y-2">
                {sortedEvents.length > EVENTS_PAGE && (
                  <div className="flex items-center justify-between px-1 text-xs">
                    <button disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-lg px-2 py-1 font-semibold text-ink-2 disabled:opacity-30">‹ 이전</button>
                    <span className="text-muted">{page + 1} / {Math.ceil(sortedEvents.length / EVENTS_PAGE)} · 예정 {upcomingCount}개 · 지난 {sortedEvents.length - upcomingCount}개</span>
                    <button disabled={(page + 1) * EVENTS_PAGE >= sortedEvents.length} onClick={() => setPage(page + 1)} className="rounded-lg px-2 py-1 font-semibold text-ink-2 disabled:opacity-30">다음 ›</button>
                  </div>
                )}
                {sortedEvents.slice(page * EVENTS_PAGE, page * EVENTS_PAGE + EVENTS_PAGE).map((e) => (
                  <div key={e.id}>
                    {e.survey_open && e.status !== 'CANCELED' && e.my_attendance === 'ATTEND' && !e.my_survey_submitted && (
                      <button onClick={() => nav(`/events/${e.id}/vote`)} className="mb-1 flex w-full items-center justify-between rounded-2xl bg-court-500 px-4 py-2.5 text-left text-sm font-semibold text-white">
                        <span>{fmtEvent(e)} - 경기 후 투표하기</span><span>→</span>
                      </button>
                    )}
                    <EventRow e={e} withDetail={!!e.adopted_candidate_id && e.event_date >= today} past={e.event_date < today} />
                    {e.adopted_candidate_id && e.event_date >= today && <AdoptedSummary eventId={e.id} isManager={isManager} />}
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="등록된 일정이 없어요"
                desc={isManager ? (t.status === 'ACTIVE' ? '첫 일정을 등록해 보세요.' : t.approval_status !== 'APPROVED' ? '관리자 승인이 끝나면 일정을 만들 수 있어요.' : `5명 이상 모이면 일정을 만들 수 있어요 (현재 ${t.member_count}명)`) : '매니저가 일정을 올리면 여기에 보여요.'}
              />
            )}
          </>
        ) : players.isLoading ? <Spinner /> : (
          <div className="space-y-2">
            <button onClick={() => nav(`/teams/${id}/leaderboard`)} className="flex w-full items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 text-left text-sm font-semibold text-ink">
              <span>리더보드 <span className="ml-1 text-[11px] font-normal text-muted">참여율 · 출전 쿼터{isManager ? ' · 기여 점수' : ''}</span></span><span>→</span>
            </button>
            {players.data?.items.map((p) => <PlayerRow key={p.id} p={p} isMe={p.id === t.my_player_id} />)}
          </div>
        )}
      </Content>
    </Screen>
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
  const qc = useQueryClient()
  const team = useQuery({ queryKey: ['team', id], queryFn: () => teamsApi.get(id) })
  const players = useQuery({ queryKey: ['team', id, 'players', 'skill'], queryFn: () => teamsApi.players(id, 'skill') })
  const [msg, setMsg] = useState<{ kind: 'error' | 'info'; text: string } | null>(null)
  const refresh = () => { qc.invalidateQueries({ queryKey: ['team', id] }); qc.invalidateQueries({ queryKey: ['me', 'teams'] }) }  // 'team', id 프리픽스로 players·merge-candidates 도 함께 갱신

  const me = useMe()
  const [open, setOpen] = useState<number | null>(null)  // 관리 메뉴가 펼쳐진 회원
  const setRole = useMutation({
    mutationFn: ({ pid, role }: { pid: number; role: 'MANAGER' | 'PLAYER' }) => teamsApi.setRole(id, pid, role),
    onSuccess: (_, v) => {
      setMsg(null); refresh(); setOpen(null)
      if (v.pid === team.data?.my_player_id && v.role === 'PLAYER') nav(`/teams/${id}`, { replace: true })  // 본인 해제 → 이 화면을 볼 수 없다
    },
    onError: (e) => { const t = errMsg(e, '권한을 바꾸지 못했어요.'); setMsg({ kind: 'error', text: t }); alert(t) },
  })
  const isOwner = !!team.data && !!me.data && team.data.owner.id === me.data.id  // 팀장 = 팀을 만든 사람. 권한 부여·회수는 팀장만
  const changeRole = (p: PlayerCard, isMe: boolean, managers: PlayerCard[]) => {
    const demote = p.role === 'MANAGER'
    if (demote) {
      const others = managers.filter((m) => m.id !== p.id)
      if (others.length === 0) { alert('매니저가 1명뿐이라 해제할 수 없어요. 먼저 다른 팀원을 매니저로 지정해 주세요.'); return }
      if (isMe) {
        const next = [...others].sort((a, b) => a.id - b.id)[0]  // 서버와 같은 규칙: 가장 먼저 매니저가 된 사람
        const ask = `내 매니저 권한을 해제하면 팀장 권한이 ${next.display_name}님에게 넘어가고, 이 팀 관리 화면에 더 이상 들어올 수 없어요. 되돌리려면 ${next.display_name}님이 다시 지정해 줘야 해요.\n\n정말 해제할까요?`
        if (!confirm(ask)) return
      }
    }
    setRole.mutate({ pid: p.id, role: demote ? 'PLAYER' : 'MANAGER' })
  }
  const [editTeam, setEditTeam] = useState(false)
  const [tf, setTf] = useState({ name: '', description: '', home_court: '' })
  const saveTeam = useMutation({
    mutationFn: () => teamsApi.update(id, { name: tf.name.trim(), description: tf.description.trim() || undefined, home_court: tf.home_court.trim() || undefined }),
    onSuccess: () => { setMsg({ kind: 'info', text: '팀 정보를 저장했어요.' }); setEditTeam(false); refresh() },
    onError: (e) => setMsg({ kind: 'error', text: errMsg(e, '저장하지 못했어요.') }),
  })
  const remove = useMutation({
    mutationFn: (pid: number) => teamsApi.remove(id, pid),
    onSuccess: () => { setMsg({ kind: 'info', text: '팀에서 제외했어요.' }); refresh() },
    onError: (e) => setMsg({ kind: 'error', text: errMsg(e, '제외하지 못했어요.') }),
  })
  const regen = useMutation({
    mutationFn: () => teamsApi.regenerateCode(id),
    onSuccess: (r) => { setMsg({ kind: 'info', text: `새 팀 코드: ${r.team_code}` }); refresh() },
  })
  const candidates = useQuery({ queryKey: ['team', id, 'merge-candidates'], queryFn: () => teamsApi.mergeCandidates(id), enabled: team.data?.my_role === 'MANAGER' })
  const merge = useMutation({
    mutationFn: ({ guest, into }: { guest: number; into: number }) => teamsApi.mergeGuest(guest, into),
    onSuccess: () => { setMsg({ kind: 'info', text: '병합했어요. 게스트 기록이 회원 계정으로 이어졌어요.' }); refresh(); qc.invalidateQueries({ queryKey: ['stats'] }) },
    onError: (e) => setMsg({ kind: 'error', text: errMsg(e, '병합하지 못했어요.') }),
  })

  const t = team.data
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
        {t && t.my_role !== 'MANAGER' && <Alert>매니저만 볼 수 있는 화면이에요.</Alert>}
        {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
        {t && (editTeam ? (
          <Card className="space-y-3">
            <Field label="팀 이름" value={tf.name} onChange={(e) => setTf({ ...tf, name: e.target.value })} maxLength={50} required />
            <Field label="팀 소개 (선택)" value={tf.description} onChange={(e) => setTf({ ...tf, description: e.target.value })} placeholder="매주 일요일 오전, 게스트 환영" />
            <Field label="홈 코트 (선택)" value={tf.home_court} onChange={(e) => setTf({ ...tf, home_court: e.target.value })} maxLength={100} />
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
            <Button variant="ghost" className="min-h-10 text-sm" onClick={() => { setTf({ name: t.name, description: t.description ?? '', home_court: t.home_court ?? '' }); setEditTeam(true) }}>수정</Button>
          </Card>
        ))}
        {t && (
          <Card className="flex items-center justify-between">
            <div>
              <p className="text-xs text-muted">팀 코드</p>
              <p className="font-mono text-xl font-black tracking-[0.25em] text-ink">{t.team_code}</p>
            </div>
            <Button variant="ghost" className="min-h-10 text-sm" loading={regen.isPending} onClick={() => confirm('기존 코드는 더 이상 쓸 수 없어요. 재발급할까요?') && regen.mutate()}>재발급</Button>
          </Card>
        )}
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted">실력 정렬</p>
            <p className="text-sm font-semibold text-ink">팀원 순서를 매기면 처음 실력에 반영돼요</p>
          </div>
          <Button variant="ghost" className="min-h-10 text-sm" onClick={() => nav(`/teams/${id}/ranking`)}>정렬하기</Button>
        </Card>
        <Card className="flex items-center justify-between">
          <div>
            <p className="text-xs text-muted">지난 기록 추가</p>
            <p className="text-sm font-semibold text-ink">앱을 쓰기 전 경기 기록 남기기</p>
          </div>
          <Button variant="ghost" className="min-h-10 text-sm" onClick={() => nav(`/teams/${id}/records/new`)}>추가하기</Button>
        </Card>

        <section>
          <SectionTitle action={
            <div className="flex gap-1">
              {([['skill', '실력'], ['position', '포지션'], ['attendance', '참여']] as const).map(([k, l]) => {
                const on = sort.key === k
                const hint = !on ? '' : k === 'position' ? (sort.desc ? ' C→PG' : ' PG→C') : sort.desc ? ' 높은순' : ' 낮은순'
                return (
                  <button key={k} onClick={() => clickSort(k)} className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${on ? 'bg-navy-800 text-white' : 'bg-sunken text-muted'}`}>
                    {l}{hint}{on ? (sort.desc ? ' ▼' : ' ▲') : ''}
                  </button>
                )
              })}
            </div>
          }>팀원 {members.length}</SectionTitle>
          {players.isLoading ? <Spinner /> : (
            <div className="space-y-2">
              {members.map((p) => {
                const isMe = p.id === t?.my_player_id
                const menu = open === p.id
                const ownerRow = !!t && p.user_id === t.owner.id
                const managers = members.filter((m) => m.role === 'MANAGER')
                return (
                  <div key={p.id}>
                    <PlayerRow
                      p={p}
                      isMe={isMe}
                      ownerRow={ownerRow}
                      right={
                        <button aria-label="관리" className={`flex size-9 items-center justify-center rounded-lg text-lg font-bold ${menu ? 'bg-navy-800 text-white' : 'bg-sunken text-ink-2'}`} onClick={() => setOpen(menu ? null : p.id)}>⋯</button>
                      }
                    />
                    {menu && (
                      <div className="-mt-1 grid grid-cols-3 gap-2 rounded-b-2xl border border-t-0 border-line bg-surface-2 px-3 py-2">
                        <button className="min-h-10 rounded-xl bg-surface text-xs font-semibold text-ink shadow-sm active:bg-sunken" onClick={() => nav(`/teams/${id}/players/${p.id}`)}>실력 보기</button>
                        {isOwner ? (
                          <button className="min-h-10 rounded-xl bg-surface text-xs font-semibold text-ink shadow-sm active:bg-sunken disabled:opacity-50" disabled={setRole.isPending} onClick={() => changeRole(p, isMe, managers)}>{p.role === 'MANAGER' ? '매니저 해제' : '매니저 지정'}</button>
                        ) : (
                          <button className="min-h-10 rounded-xl bg-surface text-xs font-semibold text-faint shadow-sm" onClick={() => alert('매니저 지정·해제는 팀장(팀을 만든 사람)만 할 수 있어요.')}>팀장 전용</button>
                        )}
                        <button className="min-h-10 rounded-xl bg-surface text-xs font-semibold text-danger-ink shadow-sm active:bg-danger-soft disabled:opacity-40" disabled={isMe} onClick={() => confirm(`${p.display_name}님을 팀에서 제외할까요?`) && remove.mutate(p.id)}>{isMe ? '본인 제외 불가' : '팀에서 제외'}</button>
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
            <Alert kind="info">게스트로 오던 사람이 회원가입한 것 같아요. 같은 사람이 맞으면 병합해 과거 기록을 이어 주세요. (이름만 같은 다른 사람일 수도 있어요)</Alert>
            <div className="mt-2 space-y-2">
              {candidates.data.items.map((c) => (
                <Card key={`${c.guest.id}-${c.member.id}`} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1 text-sm">
                    <p className="font-semibold text-ink">게스트 {c.guest.display_name} <span className="text-faint">→</span> 팀원 {c.member.display_name}</p>
                    <p className="text-xs text-muted">게스트 기록(배정·쿼터·투표)이 회원 계정으로 승계돼요. 되돌릴 수 있어요.</p>
                  </div>
                  <Button className="min-h-10 text-sm" loading={merge.isPending} onClick={() => confirm(`게스트 ${c.guest.display_name}의 기록을 ${c.member.display_name}님에게 병합할까요?`) && merge.mutate({ guest: c.guest.id, into: c.member.id })}>병합</Button>
                </Card>
              ))}
            </div>
          </section>
        )}

      </Content>
    </Screen>
  )
}
