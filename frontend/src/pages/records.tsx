/**
 * 지난 기록 추가 (매니저) — 앱을 쓰기 전 모임의 참석 · 경기 기록을 남긴다 (팀 관리 → 지난 기록 추가).
 * 1) 날짜 · 시간 · 장소 → 2) 참석한 팀원 체크 + 게스트 이름 추가 → 3) 기존 경기 기록 화면(S-15)으로 이동.
 * 일정은 2단계의 맨 아래 버튼을 누를 때 만든다 — 그 전에 나가도 빈 "지난 일정"이 남지 않게.
 * 기존 일정 · 게스트 · 쿼터 API 를 그대로 쓴다.
 */
import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { errorMessage as errMsg } from '../api/client'
import { toast } from '../store/feedback'
import { invalidateEvent } from '../lib/invalidate'
import { eventsApi } from '../api/events'
import { teamsApi } from '../api/teams'
import { localISODate, type PlayerCard } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, Field, LoadError, SectionTitle, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'

type GuestChoice = { existing_player_id: number } | { force_new: true }
type LocalGuest = { key: number; name: string; height: number | null }

export function PastRecordPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const nav = useNavigate()
  const qc = useQueryClient()
  const [step, setStep] = useState<1 | 2>(1)
  const [f, setF] = useState({ title: '', event_date: '', start_time: '10:00', end_time: '12:00', venue: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const players = useQuery({ queryKey: ['team', id, 'players'], queryFn: () => teamsApi.players(id), enabled: step === 2 })
  const [attending, setAttending] = useState<number[]>([])
  const [guests, setGuests] = useState<LocalGuest[]>([])
  const [guestName, setGuestName] = useState('')
  const [guestHeight, setGuestHeight] = useState('')
  // 저장하다 중간에 실패했을 때 다시 누르면 이어서 하도록, 이미 만든 일정과 반영한 사람을 기억한다
  const [eventId, setEventId] = useState<number | null>(null)
  const [synced, setSynced] = useState<number[]>([])
  const [sent, setSent] = useState<number[]>([])
  const [similar, setSimilar] = useState<{ guest: LocalGuest; items: PlayerCard[] } | null>(null)

  const members = players.data?.items.filter((p) => p.kind === 'MEMBER') ?? []
  const count = attending.length + guests.length

  const addGuest = () => {
    if (!guestName.trim()) return
    setGuests([...guests, { key: Date.now(), name: guestName.trim(), height: guestHeight ? Number(guestHeight) : null }])
    setGuestName(''); setGuestHeight('')
  }

  // 일정 만들기 → 참석 반영 → 게스트 등록. 같은 이름의 지난 게스트가 있으면 멈추고 같은 사람인지 묻는다(pick 으로 이어서)
  const save = useMutation({
    mutationFn: async (pick?: { key: number; choice: GuestChoice }) => {
      const payload = { title: f.title || '지난 일정', event_date: f.event_date, start_time: f.start_time || undefined, end_time: f.end_time || undefined, venue: f.venue || undefined }
      const ev = eventId === null ? await eventsApi.create(id, payload) : await eventsApi.update(eventId, payload)
      setEventId(ev.id)
      for (const m of members) {
        const on = attending.includes(m.id)
        if (on === synced.includes(m.id)) continue
        await eventsApi.setAttendance(ev.id, m.id, on ? 'ATTEND' : 'ABSENT')
        setSynced((prev) => (on ? [...prev, m.id] : prev.filter((x) => x !== m.id)))
      }
      for (const g of guests) {
        if (sent.includes(g.key)) continue
        const r = await eventsApi.registerGuest(ev.id, { display_name: g.name, height_cm: g.height, team_lock_request: false, ...(pick?.key === g.key ? pick.choice : {}) })
        if (r.kind === 'similar') return { ask: { guest: g, items: r.similar } }
        setSent((prev) => [...prev, g.key])
      }
      return { done: ev.id }
    },
    onSuccess: (r) => {
      if (r.ask) { setSimilar(r.ask); return }
      invalidateEvent(qc, r.done, id)
      nav(`/events/${r.done}/quarters`, { replace: true })
    },
    onError: (e) => toast(errMsg(e, eventId === null ? '일정을 만들지 못했어요.' : '저장하다 멈췄어요. 다시 눌러 주세요.'), 'error'),
    onSettled: (r) => { if (!r?.ask) setSimilar(null) },
  })

  if (step === 1) {
    return (
      <Screen>
        <TopBar title="지난 기록 추가" back={`/teams/${id}/members`} />
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); setStep(2) }} className="flex flex-1 flex-col">
          <Content>
            <Alert kind="info">앱을 쓰기 전에 했던 경기를 남겨요. 날짜와 참석한 사람을 고르고 쿼터 점수를 적으면 실력에 그대로 반영돼요.</Alert>
            <Field label="제목 (선택)" value={f.title} onChange={set('title')} placeholder="지난 일정" />
            <Field label="날짜" type="date" value={f.event_date} onChange={set('event_date')} max={localISODate()} required />
            <div className="grid grid-cols-2 gap-3">
              <Field label="시작" type="time" value={f.start_time} onChange={set('start_time')} />
              <Field label="종료" type="time" value={f.end_time} onChange={set('end_time')} />
            </div>
            <Field label="장소 (선택)" value={f.venue} onChange={set('venue')} />
          </Content>
          <BottomAction><Button type="submit" full disabled={!f.event_date}>다음 · 참석한 사람 고르기</Button></BottomAction>
        </form>
      </Screen>
    )
  }

  return (
    <Screen>
      {/* 뒤로는 날짜 단계로 — 고른 사람은 그대로 남는다 */}
      <TopBar title="참석한 사람" back={`/teams/${id}/members`} beforeBack={() => { setStep(1); return false }} />
      <Content>
        <section>
          <SectionTitle>팀원 · 참석 {attending.length}명</SectionTitle>
          {players.isLoading ? <Spinner /> : !players.data ? (
            <LoadError message={errMsg(players.error, '팀원을 불러오지 못했어요.')} onRetry={() => players.refetch()} retrying={players.isFetching} />
          ) : (
            <Card className="divide-y divide-line p-0">
              {members.map((p) => {
                const on = attending.includes(p.id)
                return (
                  <label key={p.id} className="flex min-h-12 items-center gap-3 px-4 py-2">
                    <input type="checkbox" checked={on} disabled={save.isPending} onChange={() => setAttending(on ? attending.filter((x) => x !== p.id) : [...attending, p.id])} className="size-5 accent-brand" />
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
                  <span key={g.key} className={`inline-flex items-center rounded-full bg-sunken pl-2.5 text-xs font-semibold text-ink ${sent.includes(g.key) ? 'pr-2.5' : ''}`}>
                    {g.name}
                    {/* 이미 일정에 넣은 게스트는 여기서 빼지 않는다 (경기 기록 화면의 명단에서 뺄 수 있다) */}
                    {!sent.includes(g.key) && <button className="-my-2 flex min-h-11 min-w-9 items-center justify-center text-faint" onClick={() => { setGuests(guests.filter((x) => x.key !== g.key)); if (similar?.guest.key === g.key) setSimilar(null) }} disabled={save.isPending} aria-label={`${g.name} 빼기`}>×</button>}
                  </span>
                ))}
              </div>
            )}
            {similar ? (
              <div className="space-y-2">
                <p className="text-sm text-ink">{similar.guest.name} — 같은 이름의 게스트가 있어요. 같은 사람이면 골라 주세요. 기록이 이어져요.</p>
                {similar.items.map((p) => (
                  <button key={p.id} disabled={save.isPending} onClick={() => save.mutate({ key: similar.guest.key, choice: { existing_player_id: p.id } })} className="flex min-h-11 w-full items-center gap-3 rounded-xl border border-line px-3 py-2 text-left active:bg-surface-2 disabled:opacity-50">
                    <Avatar name={p.display_name} src={p.profile_image_url} size="sm" />
                    <span className="flex-1 text-sm font-semibold text-ink">{p.display_name}</span>
                    <Badge>{p.playable_positions.join(' · ') || '포지션 없음'}</Badge>
                    <span className="text-xs font-semibold text-brand-ink">같은 사람</span>
                  </button>
                ))}
                <Button variant="secondary" full className="text-sm" loading={save.isPending} onClick={() => save.mutate({ key: similar.guest.key, choice: { force_new: true } })}>다른 사람 · 새 게스트로 추가</Button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input value={guestName} onChange={(e) => setGuestName(e.target.value)} aria-label="게스트 이름" placeholder="게스트 이름을 입력해 주세요" maxLength={50} className="min-h-11 min-w-0 flex-1 rounded-xl border border-line-field px-3.5 text-base outline-none focus:ring-2 focus:ring-brand/25 focus:border-brand" onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addGuest() } }} />
                <input value={guestHeight} onChange={(e) => setGuestHeight(e.target.value.replace(/\D/g, '').slice(0, 3))} inputMode="numeric" aria-label="게스트 키 (cm)" placeholder="키(cm)" className="min-h-11 w-20 rounded-xl border border-line-field px-3 text-base outline-none focus:ring-2 focus:ring-brand/25 focus:border-brand" />
                <Button variant="secondary" disabled={!guestName.trim() || save.isPending} onClick={addGuest}>추가</Button>
              </div>
            )}
          </Card>
        </section>
        <p className="px-1 text-xs text-muted">팀을 나누지 않은 기록이라, 쿼터마다 블랙 · 화이트에서 뛴 5명을 직접 골라요.</p>
      </Content>
      <BottomAction>
        {count < 10 && <p className="mb-2 text-center text-xs text-muted">참석 10명부터 기록할 수 있어요 · 지금 {count}명</p>}
        <Button full disabled={count < 10 || similar !== null} loading={save.isPending} onClick={() => save.mutate(undefined)}>경기 기록하러 가기</Button>
      </BottomAction>
    </Screen>
  )
}
