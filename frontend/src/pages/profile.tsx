/**
 * S-17 내 프로필 · 기록 (/me). 홈 번들이 가벼워지도록 따로 둔다 — 첫 화면(홈)에서는 불러오지 않는다.
 */
/** S-04 홈 (역할별) · S-17 내 프로필 · 내 팀 목록. */
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { toAvatarDataUrl } from '../lib/image'
import { peerApi } from '../api/peer'
import { MarginTrend, QuarterList } from '../components/stats'
import { surveyApi } from '../api/survey'
import { POSITIONS, SELF_RANK_LABEL, type Position, type UserDetail } from '../api/types'
import { useAuthStore } from '../store/auth'
import { Alert, Avatar, Badge, Button, Card, EmptyState, Field, GradeDot, SectionTitle, Spinner } from '../components/ui'
import { Content, Screen, TabBar, TopBar } from '../components/layout'
import { startKakao } from './auth'

import { useMe } from './home'

export function ProfilePage() {
  const me = useMe()
  const profile = useQuery({ queryKey: ['profile'], queryFn: surveyApi.myProfile })
  const logout = useAuthStore((s) => s.logout)
  const nav = useNavigate()
  const u = me.data
  const p = profile.data
  const [chosen, setChosen] = useState<number | null>(null)
  // 기록이 있는 팀을 먼저, 그 안에서는 기본 팀을 먼저 — 기본 팀에 아직 쿼터가 없으면 빈 화면 대신 기록 있는 팀이 먼저 보인다
  const teams = [...(p?.teams ?? [])].sort((a, b) =>
    (Number(b.quarters_played > 0) - Number(a.quarters_played > 0)) || (Number(b.team_id === u?.primary_team_id) - Number(a.team_id === u?.primary_team_id)))
  const current = teams.find((t) => t.team_id === chosen) ?? teams[0]
  return (
    <Screen>
      <TopBar title="내 프로필" />
      <Content>
        {!u ? <Spinner /> : (
          <>
            <Card className="flex items-center gap-4">
              <AvatarEditor user={u} />
              <div className="min-w-0 flex-1">
                <p className="text-lg font-bold text-ink">{u.nickname ?? u.name}</p>
                <p className="truncate text-sm text-muted">{u.email ?? '이메일 없음 (카카오 계정)'}</p>
                <div className="mt-1.5 flex gap-1.5">
                  {u.identities.map((i) => <Badge key={i.provider} tone={i.provider === 'KAKAO' ? 'warn' : 'navy'}>{i.provider === 'KAKAO' ? '카카오' : '이메일'}</Badge>)}
                  {!u.identities.some((i) => i.provider === 'KAKAO') && (
                    <button onClick={() => startKakao('link', (m) => alert(m))} className="rounded-full bg-[#FEE500] px-2.5 py-0.5 text-xs font-semibold text-[#191919]">카카오 연결</button>
                  )}
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
                  <div><p className="font-semibold text-ink">설문을 마쳐 주세요</p><p className="text-xs text-muted">실력·포지션 프로필이 아직 없어요.</p></div>
                  <Button onClick={() => nav('/survey')}>설문하기</Button>
                </Card>
              )}
            </section>

            {teams.length > 1 && (
              <div className="flex gap-1.5 overflow-x-auto px-1">
                {teams.map((t) => (
                  <button key={t.team_id} onClick={() => setChosen(t.team_id)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${current?.team_id === t.team_id ? 'bg-navy-800 text-white' : 'bg-sunken text-muted'}`}>
                    {t.team_name}{u?.primary_team_id === t.team_id ? ' (기본)' : ''}
                  </button>
                ))}
              </div>
            )}

            {current && (
              <section className="space-y-2">
                <SectionTitle>{teams.length > 1 ? `${current.team_name} 설정` : '팀별 설정'}</SectionTitle>
                {/* 내 등급은 나에게만 보인다. 다른 사람 카드에는 등급이 실리지 않는다 (9.2절 표시 정책) */}
                <Card className="flex items-center gap-3">
                  <GradeDot grade={current.skill_grade} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-ink">내 실력 등급</p>
                    <p className="text-xs text-muted">
                      {current.skill_grade
                        ? '나만 볼 수 있어요. 경기 기록이 쌓이면 달라져요.'
                        : '설문과 경기 기록이 쌓이면 등급이 생겨요.'}
                    </p>
                  </div>
                </Card>
                <Card className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-muted">이 동호회에서 내 실력 위치</p>
                    {current.self_rank_level ? (
                      <p className="mt-0.5"><Badge tone="court">{SELF_RANK_LABEL[current.self_rank_level]}</Badge></p>
                    ) : (
                      <p className="mt-0.5 text-sm font-semibold text-brand-ink">아직 안 알려줬어요 — 배정 정확도에 가장 큰 영향을 줘요</p>
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
                <EmptyState title="아직 경기 기록이 없어요" desc="팀에 가입하고 경기 기록이 쌓이면 여기에 나와요." />
              </section>
            )}

            <Card onClick={() => nav('/help')} label="도움말 · 문의" className="flex items-center justify-between gap-3">
              <div><p className="font-semibold text-ink">도움말 · 문의</p><p className="text-xs text-muted">기능 설명, 실력 공개 범위, 개발자 연락처</p></div>
              <span className="text-faint" aria-hidden="true">→</span>
            </Card>

            <AccountSection user={u} onLoggedOut={() => { logout(); nav('/login', { replace: true }) }} />
          </>
        )}
      </Content>
      <TabBar />
    </Screen>
  )
}

/** 계정 관리 — 비밀번호 변경(이메일 로그인 계정만), 로그아웃, 계정 삭제 */
function AccountSection({ user, onLoggedOut }: { user: UserDetail; onLoggedOut: () => void }) {
  const hasPassword = user.identities.some((i) => i.provider === 'LOCAL')
  const [open, setOpen] = useState(false)
  const [cur, setCur] = useState('')
  const [nw, setNw] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const change = useMutation({
    mutationFn: () => authApi.changePassword(cur, nw),
    onSuccess: () => { setMsg('비밀번호를 바꿨어요.'); setOpen(false); setCur(''); setNw('') },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : '바꾸지 못했어요.'),
  })
  const remove = useMutation({
    mutationFn: authApi.deleteMe,
    onSuccess: () => { alert('계정을 삭제했어요. 그동안 고마웠어요.'); onLoggedOut() },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : '삭제하지 못했어요.'),
  })
  return (
    <section className="space-y-2">
      <SectionTitle>계정</SectionTitle>
      {msg && <Alert kind={msg.includes('바꿨어요') ? 'info' : 'error'}>{msg}</Alert>}
      {hasPassword ? (
        <Card className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-ink">비밀번호 변경</p>
            <Button variant="ghost" className="min-h-10 text-sm" onClick={() => setOpen((o) => !o)}>{open ? '닫기' : '바꾸기'}</Button>
          </div>
          {open && (
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); change.mutate() }}>
              <Field label="현재 비밀번호" type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required />
              <Field label="새 비밀번호" type="password" value={nw} onChange={(e) => setNw(e.target.value)} autoComplete="new-password" minLength={8} maxLength={72} required hint="8자 이상" />
              <Button type="submit" full loading={change.isPending} disabled={cur.length === 0 || nw.length < 8}>저장</Button>
            </form>
          )}
        </Card>
      ) : (
        <Card><p className="text-sm text-muted">카카오로만 로그인하는 계정이에요. 이메일 비밀번호를 만들려면 로그인 화면의 '비밀번호 찾기'를 써 주세요.</p></Card>
      )}
      <Button variant="danger" full onClick={onLoggedOut}>로그아웃</Button>
      <button
        className="w-full py-2 text-center text-xs text-faint underline underline-offset-2"
        disabled={remove.isPending}
        onClick={() => confirm('계정을 삭제할까요? 이메일·이름·사진이 지워지고 팀에서 나가요. 경기 기록은 "탈퇴한 회원"으로 남아요.') && confirm('되돌릴 수 없어요. 정말 삭제할까요?') && remove.mutate()}
      >
        계정 삭제
      </button>
    </section>
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
          {current.length === 0 && <span className="text-sm text-muted">포지션 정보 없음</span>}
          {current.map((pos, i) => <Badge key={pos} tone={i === 0 ? 'court' : 'navy'}>{i === 0 ? `${pos} 선호` : pos}</Badge>)}
        </div>
        <Button variant="ghost" className="min-h-10 text-sm" onClick={() => { setOrder(current); setEditing(true) }}>수정</Button>
      </Card>
    )
  }
  return (
    <Card className="space-y-3">
      <p className="text-sm text-muted">할 수 있는 포지션을 <b>선호하는 순서대로</b> 눌러 주세요. 다시 누르면 빠져요.</p>
      <div className="flex gap-1.5">
        {POSITIONS.map((pos) => {
          const idx = order.indexOf(pos)
          return (
            <button key={pos} type="button" onClick={() => setOrder(idx >= 0 ? order.filter((x) => x !== pos) : [...order, pos])}
              className={`relative min-h-11 flex-1 rounded-lg border text-sm font-bold ${idx >= 0 ? 'border-court-500 bg-court-500 text-white' : 'border-line bg-surface text-ink'}`}>
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
            <div><p className="text-2xl font-black text-ink">{s.events_attended}</p><p className="text-[11px] text-muted">참석 일정</p></div>
            <div><p className="text-2xl font-black text-ink">{s.quarters_played}</p><p className="text-[11px] text-muted">출전 쿼터</p></div>
            <div><p className="text-2xl font-black text-brand-ink">{s.margin_trend.reduce((a, m) => a + m.wins, 0)}<span className="text-sm text-faint">/{s.quarters_played}</span></p><p className="text-[11px] text-muted">이긴 쿼터</p></div>
          </Card>
          <MarginTrend points={s.margin_trend} />
          <QuarterList records={s.recent_quarters} />
        </div>
      )}
    </section>
  )
}

/** D-day 표기: 오늘 = D-DAY, 내일 = D-1 */
/** 프로필 사진 — 눌러서 고르고, 256px 로 줄여 올린다. 사진이 있으면 길게 누르지 않아도 바로 지울 수 있게 X 를 띄운다 */
function AvatarEditor({ user }: { user: UserDetail }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState<string | null>(null)
  const done = () => { qc.invalidateQueries({ queryKey: ['me'] }); qc.invalidateQueries({ queryKey: ['team'] }) }
  const upload = useMutation({
    mutationFn: async (file: File) => authApi.setAvatar(await toAvatarDataUrl(file)),
    onSuccess: () => { setErr(null); done() },
    onError: (e) => setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : '사진을 올리지 못했어요.'),
  })
  const remove = useMutation({ mutationFn: authApi.deleteAvatar, onSuccess: done })
  const busy = upload.isPending || remove.isPending
  return (
    <div className="shrink-0">
      <div className="relative">
        <button
          type="button" onClick={() => fileRef.current?.click()} disabled={busy}
          aria-label={user.profile_image_url ? '프로필 사진 바꾸기' : '프로필 사진 추가하기'}
          className="relative block rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
        >
          <Avatar name={user.nickname ?? user.name} src={user.profile_image_url} size="xl" />
          <span className="absolute -bottom-0.5 -right-0.5 flex size-7 items-center justify-center rounded-full border-2 border-white bg-court-500 text-xs font-bold text-white">
            {busy ? '…' : user.profile_image_url ? '✎' : '+'}
          </span>
        </button>
        {user.profile_image_url && !busy && (
          <button
            type="button" onClick={() => confirm('프로필 사진을 지울까요?') && remove.mutate()}
            aria-label="프로필 사진 삭제"
            className="absolute -right-1 -top-1 flex size-6 items-center justify-center rounded-full border border-line bg-surface text-xs text-muted shadow-sm"
          >
            ×
          </button>
        )}
      </div>
      <input
        ref={fileRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) upload.mutate(f) }}
      />
      {err && <p className="mt-1 w-20 text-[11px] leading-tight text-danger-ink">{err}</p>}
    </div>
  )
}
