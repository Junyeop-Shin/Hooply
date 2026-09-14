/**
 * 지난 기록 추가 (매니저) — 앱을 쓰기 전 모임의 참석·쿼터 기록을 남긴다 (팀 관리 → 지난 기록 추가).
 * 1) 일자·시간·장소로 일정 생성 → 2) 참석 인원 체크 + 게스트 이름 추가(같은 이름의 지난 게스트가 있으면 같은 사람인지 확인)
 * → 3) 기존 쿼터 기록 화면(S-15)으로 이동. 기존 일정·게스트·쿼터 API 를 그대로 쓴다.
 */
import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { eventsApi } from '../api/events'
import { teamsApi } from '../api/teams'
import { localISODate, type PlayerCard } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, Field, SectionTitle, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

export function PastRecordPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const nav = useNavigate()
  const qc = useQueryClient()
  const [eventId, setEventId] = useState<number | null>(null)
  const [f, setF] = useState({ title: '', event_date: '', start_time: '10:00', end_time: '12:00', venue: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const [msg, setMsg] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => eventsApi.create(id, { title: f.title || '지난 일정', event_date: f.event_date, start_time: f.start_time || undefined, end_time: f.end_time || undefined, venue: f.venue || undefined }),
    onSuccess: (ev) => { qc.invalidateQueries({ queryKey: ['events'] }); setEventId(ev.id) },
    onError: (e) => setMsg(errMsg(e, '일정을 만들지 못했어요.')),
  })

  if (eventId === null) {
    return (
      <Screen>
        <TopBar title="지난 기록 추가" back={`/teams/${id}/members`} />
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate() }} className="flex flex-1 flex-col">
          <Content>
            <Alert kind="info">앱을 쓰기 전에 했던 경기를 남겨요. 일정을 만들고 참석한 사람을 고른 뒤 쿼터를 입력하면 실력에 그대로 반영돼요.</Alert>
            <Field label="제목 (선택)" value={f.title} onChange={set('title')} placeholder="지난 일정" />
            <Field label="날짜" type="date" value={f.event_date} onChange={set('event_date')} max={localISODate()} required />
            <div className="grid grid-cols-2 gap-3">
              <Field label="시작" type="time" value={f.start_time} onChange={set('start_time')} />
              <Field label="종료" type="time" value={f.end_time} onChange={set('end_time')} />
            </div>
            <Field label="장소 (선택)" value={f.venue} onChange={set('venue')} />
            {msg && <Alert>{msg}</Alert>}
          </Content>
          <BottomAction><Button type="submit" full loading={create.isPending} disabled={!f.event_date}>다음 · 참석 인원 고르기</Button></BottomAction>
        </form>
      </Screen>
    )
  }
  return <AttendeeStep teamId={id} eventId={eventId} onDone={() => nav(`/events/${eventId}/quarters`, { replace: true })} />
}

function AttendeeStep({ teamId, eventId, onDone }: { teamId: number; eventId: number; onDone: () => void }) {
  const qc = useQueryClient()
  const players = useQuery({ queryKey: ['team', teamId, 'players'], queryFn: () => teamsApi.players(teamId) })
  const att = useQuery({ queryKey: ['events', eventId, 'attendances'], queryFn: () => eventsApi.attendances(eventId) })
  const [msg, setMsg] = useState<string | null>(null)
  const [guestName, setGuestName] = useState('')
  const [guestHeight, setGuestHeight] = useState('')
  const [similar, setSimilar] = useState<PlayerCard[] | null>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: ['events', eventId] })

  const attending = new Set(att.data?.items.filter((a) => a.status === 'ATTEND').map((a) => a.player.id) ?? [])
  const toggle = useMutation({
    mutationFn: ({ pid, on }: { pid: number; on: boolean }) => eventsApi.setAttendance(eventId, pid, on ? 'ATTEND' : 'ABSENT'),
    onSuccess: refresh,
    onError: (e) => setMsg(errMsg(e, '바꾸지 못했어요.')),
  })
  const addGuest = useMutation({
    mutationFn: (extra: { existing_player_id?: number; force_new?: boolean }) => eventsApi.registerGuest(eventId, { display_name: guestName.trim(), height_cm: guestHeight ? Number(guestHeight) : null, team_lock_request: false, ...extra }),
    onSuccess: (r) => { if (r.kind === 'similar') setSimilar(r.similar); else { setSimilar(null); setGuestName(''); setGuestHeight(''); refresh() } },
    onError: (e) => setMsg(errMsg(e, '게스트를 추가하지 못했어요.')),
  })
  const removeGuest = useMutation({ mutationFn: (pid: number) => eventsApi.removeGuest(eventId, pid), onSuccess: refresh })

  const members = players.data?.items.filter((p) => p.kind === 'MEMBER') ?? []
  const guests = att.data?.items.filter((a) => a.player.kind === 'GUEST' && a.status === 'ATTEND') ?? []
  const count = attending.size

  return (
    <Screen>
      <TopBar title="참석 인원" back={`/teams/${teamId}/members`} />
      <Content>
        {msg && <Alert>{msg}</Alert>}
        <section>
          <SectionTitle>팀원 · 참석 {members.filter((m) => attending.has(m.id)).length}명</SectionTitle>
          {players.isLoading || att.isLoading ? <Spinner /> : (
            <Card className="divide-y divide-line p-0">
              {members.map((p) => {
                const on = attending.has(p.id)
                return (
                  <label key={p.id} className="flex min-h-12 items-center gap-3 px-4 py-2">
                    <input type="checkbox" checked={on} onChange={() => toggle.mutate({ pid: p.id, on: !on })} className="size-5 accent-brand" />
                    <Avatar name={p.display_name} src={p.profile_image_url} size="sm" />
                    <span className="flex-1 text-sm font-semibold text-ink">{p.display_name}</span>
                    <span className="text-xs text-faint">{p.primary_position ?? ''}</span>
                  </label>
                )
              })}
            </Card>
          )}
        </section>

        <section>
          <SectionTitle>게스트 · {guests.length}명</SectionTitle>
          <Card className="space-y-3">
            {guests.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {guests.map((g) => (
                  <span key={g.player.id} className="inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-1 text-xs font-semibold text-ink">
                    {g.player.display_name}
                    <button className="text-faint" onClick={() => removeGuest.mutate(g.player.id)} aria-label="빼기">×</button>
                  </span>
                ))}
              </div>
            )}
            {similar ? (
              <div className="space-y-2">
                <p className="text-sm text-ink">같은 이름의 게스트가 있어요. 같은 사람이면 골라 주세요. 기록이 이어져요.</p>
                {similar.map((p) => (
                  <button key={p.id} onClick={() => addGuest.mutate({ existing_player_id: p.id })} className="flex w-full items-center gap-3 rounded-xl border border-line px-3 py-2 text-left active:bg-surface-2">
                    <Avatar name={p.display_name} src={p.profile_image_url} size="sm" />
                    <span className="flex-1 text-sm font-semibold text-ink">{p.display_name}</span>
                    <Badge>{p.playable_positions.join(' · ') || '포지션 없음'}</Badge>
                    <span className="text-xs font-semibold text-brand-ink">같은 사람</span>
                  </button>
                ))}
                <div className="flex gap-2">
                  <Button variant="ghost" className="min-h-10 text-sm" onClick={() => setSimilar(null)}>취소</Button>
                  <Button variant="secondary" full className="min-h-10 text-sm" loading={addGuest.isPending} onClick={() => addGuest.mutate({ force_new: true })}>다른 사람 · 새 게스트로 추가</Button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <input value={guestName} onChange={(e) => setGuestName(e.target.value)} placeholder="게스트 이름을 입력해 주세요" maxLength={50} className="min-h-11 flex-1 rounded-xl border border-line px-3.5 text-[15px] outline-none focus:ring-2 focus:ring-brand-line" onKeyDown={(e) => { if (e.key === 'Enter' && guestName.trim()) { e.preventDefault(); addGuest.mutate({}) } }} />
                <input value={guestHeight} onChange={(e) => setGuestHeight(e.target.value.replace(/\D/g, '').slice(0, 3))} inputMode="numeric" placeholder="키(cm)" className="min-h-11 w-20 rounded-xl border border-line px-3 text-[15px] outline-none focus:ring-2 focus:ring-brand-line" />
                <Button variant="secondary" className="min-h-11" disabled={!guestName.trim()} loading={addGuest.isPending} onClick={() => addGuest.mutate({})}>추가</Button>
              </div>
            )}
          </Card>
        </section>
        <p className="px-1 text-xs text-muted">쿼터를 기록하려면 참석 인원이 10명 이상이어야 해요. 배정 없이 기록하므로 쿼터마다 블랙·화이트 출전 5명을 직접 고르게 돼요.</p>
      </Content>
      <BottomAction>
        <Button full disabled={count < 10} onClick={onDone}>{count < 10 ? `쿼터 기록하기 (참석 10명 이상 필요 · 현재 ${count}명)` : `쿼터 기록하러 가기 (${count}명)`}</Button>
      </BottomAction>
    </Screen>
  )
}
