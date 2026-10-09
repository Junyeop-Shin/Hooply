/**
 * S-09 일정 등록 · S-10 일정 상세/RSVP · S-11 참석자 현황·게스트 등록 (F4, F13, guest-feature-spec 6절).
 * 게스트 등록 바텀시트는 플레이어(S-10)와 매니저(S-11)가 같은 컴포넌트를 쓴다.
 */
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { errorMessage as errMsg } from '../api/client'
import { eventsApi } from '../api/events'
import { peerApi } from '../api/peer'
import { announceShare, shareText } from '../lib/kakao'
import { POSITIONS, localISODate, type AttendanceView, type EventGuestInput, type EventGuestUpdate, type EventView, type GuestPreset, type PlayerCard, type Position } from '../api/types'
import { invalidateEvent } from '../lib/invalidate'
import { confirm, toast } from '../store/feedback'
import { CLOSE_RSVP_CONFIRM } from '../lib/copy'
import { fmtEvent } from '../lib/format'
import { Alert, Avatar, Badge, Button, Card, Field, GradeDot, LoadError, Sheet, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar, useFinish, useGoBack } from '../components/layout'
import { EventTactics } from '../components/tactics'
import { AdoptedSection } from '../components/adopted'



/* ---------- S-09 일정 등록 ---------- */

/** "20:00" → 1200(분). 값이 없거나 형식이 다르면 null */
function toMinutes(hhmm: string): number | null {
  const [h, m] = (hhmm ?? '').split(':').map(Number)
  return Number.isNaN(h) || Number.isNaN(m) ? null : h * 60 + m
}

/** "20:00" 에 분을 더한다. 자정을 넘으면 23:59 로 멈춘다 (일정은 하루 안에서 끝나는 것으로 다룬다) */
function addMinutes(hhmm: string, minutes: number): string {
  const base = toMinutes(hhmm)
  if (base === null) return hhmm
  const total = Math.min(base + minutes, 24 * 60 - 1)
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

const DEFAULT_DURATION_MIN = 120

const EMPTY_EVENT = { title: '', event_date: '', start_time: '20:00', end_time: '22:00', venue: '', rsvp_date: '', rsvp_time: '', memo: '' }

export function EventCreatePage() {
  const { teamId, eventId } = useParams()
  const editId = eventId ? Number(eventId) : null  // /events/:eventId/edit — 같은 폼을 수정에 쓴다
  const existing = useQuery({ queryKey: ['events', editId], queryFn: () => eventsApi.get(editId!), enabled: editId !== null })
  const id = editId !== null ? (existing.data?.team_id ?? 0) : Number(teamId)
  const nav = useNavigate()
  const finish = useFinish()
  const qc = useQueryClient()
  const [f, setF] = useState(EMPTY_EVENT)
  const [prefilled, setPrefilled] = useState(false)
  // 시작 시각을 바꾸면 종료도 같은 간격만큼 따라온다. 기본 2시간이고, 종료를 직접 고치거나 지난 일정을 채우면
  // 그 길이를 기억해 이후 시작 변경에도 유지한다 (3시간짜리 모임이 2시간으로 줄어들지 않게)
  const [durationMin, setDurationMin] = useState(DEFAULT_DURATION_MIN)
  useEffect(() => {
    if (!existing.data || prefilled) return
    const e = existing.data
    const dl = e.rsvp_deadline ? new Date(e.rsvp_deadline) : null
    const pad = (n: number) => String(n).padStart(2, '0')
    setF({
      title: e.title ?? '', event_date: e.event_date, start_time: e.start_time?.slice(0, 5) ?? '', end_time: e.end_time?.slice(0, 5) ?? '',
      venue: e.venue ?? '', rsvp_date: dl ? localISODate(dl) : '', rsvp_time: dl ? `${pad(dl.getHours())}:${pad(dl.getMinutes())}` : '', memo: e.memo ?? '',
    })
    const s = toMinutes(e.start_time?.slice(0, 5) ?? ''), en = toMinutes(e.end_time?.slice(0, 5) ?? '')
    if (s !== null && en !== null && en > s) setDurationMin(en - s)  // 고치는 일정의 길이를 기억한다
    setPrefilled(true)
  }, [existing.data, prefilled])
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((prev) => ({ ...prev, [k]: e.target.value }))
  const setStart = (e: { target: { value: string } }) => {
    const v = e.target.value
    setF((prev) => ({ ...prev, start_time: v, end_time: v ? addMinutes(v, durationMin) : prev.end_time }))
  }
  const setEnd = (e: { target: { value: string } }) => {
    const v = e.target.value
    const gap = toMinutes(v) !== null && toMinutes(f.start_time) !== null ? toMinutes(v)! - toMinutes(f.start_time)! : null
    if (gap !== null && gap > 0) setDurationMin(gap)
    setF((prev) => ({ ...prev, end_time: v }))
  }
  // 마감 날짜만 고르면 시각은 밤 10시로 채워 둔다 (비워 두면 마감이 안 걸린다)
  const setRsvpDate = (e: { target: { value: string } }) => {
    const v = e.target.value
    setF((prev) => ({ ...prev, rsvp_date: v, rsvp_time: v && !prev.rsvp_time ? '22:00' : prev.rsvp_time }))
  }

  // 지난 일정 불러오기: 제목·시작/종료·장소·메모는 그대로, 날짜와 응답 마감은 그 일정 기준 +7일. 입력만 채우고 저장은 하지 않는다
  const recent = useQuery({ queryKey: ['events', 'team', id, 'all', 50], queryFn: () => eventsApi.list(id, { size: 50 }), enabled: editId === null && id > 0 })
  const lastEvent = (recent.data?.items ?? []).filter((e) => e.status !== 'CANCELED').sort((a, b) => b.event_date.localeCompare(a.event_date) || b.id - a.id)[0]
  const [loadedFrom, setLoadedFrom] = useState<string | null>(null)
  const loadFromLast = () => {
    if (!lastEvent) return
    const plus7 = (d: Date) => new Date(d.getTime() + 7 * 86_400_000)
    const deadline = lastEvent.rsvp_deadline ? plus7(new Date(lastEvent.rsvp_deadline)) : null
    const pad = (n: number) => String(n).padStart(2, '0')
    const start = lastEvent.start_time?.slice(0, 5) ?? ''
    const end = lastEvent.end_time?.slice(0, 5) ?? ''
    setF({
      title: lastEvent.title ?? '',
      event_date: localISODate(plus7(new Date(lastEvent.event_date + 'T00:00:00'))),
      start_time: start,
      end_time: end,
      venue: lastEvent.venue ?? '',
      rsvp_date: deadline ? localISODate(deadline) : '',
      rsvp_time: deadline ? `${pad(deadline.getHours())}:${pad(deadline.getMinutes())}` : '',
      memo: lastEvent.memo ?? '',
    })
    const gap = start && end ? (toMinutes(end)! - toMinutes(start)!) : null
    setDurationMin(gap && gap > 0 ? gap : DEFAULT_DURATION_MIN)  // 불러온 일정의 진행 시간을 유지한다
    setLoadedFrom(fmtEvent(lastEvent))
  }

  const payload = () => ({
    title: f.title || undefined, event_date: f.event_date, start_time: f.start_time || undefined, end_time: f.end_time || undefined,
    venue: f.venue || undefined,
    rsvp_deadline: f.rsvp_date ? new Date(`${f.rsvp_date}T${f.rsvp_time || '22:00'}`).toISOString() : undefined,
    memo: f.memo || undefined,
  })
  const m = useMutation({
    mutationFn: () => (editId !== null ? eventsApi.update(editId, payload()) : eventsApi.create(id, payload())),
    // 등록은 새 화면으로 바꿔치기, 수정은 들어온 일정 화면으로 한 칸 되감는다 — 뒤로가 수정 화면이나 같은 일정으로 가지 않게
    onSuccess: (ev) => {
      invalidateEvent(qc, ev.id, ev.team_id)
      if (editId !== null) { finish(`/events/${ev.id}`, 1); return }
      qc.invalidateQueries({ queryKey: ['me', 'tutorial'] })  // 시작 안내 "첫 일정 만들기" 단계가 바로 끝난 것으로
      nav(`/events/${ev.id}`, { replace: true })
    },
    meta: { inlineError: true },
  })

  return (
    <Screen>
      <TopBar title={editId !== null ? '일정 고치기' : '일정 등록'} back={editId !== null ? `/events/${editId}` : `/teams/${id}`} />
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate() }} className="flex flex-1 flex-col">
        <Content>
          {editId !== null && <Alert kind="info">응답은 그대로 남아요. 날짜나 시간을 바꿨다면 팀원에게 알려 주세요.</Alert>}
          {loadedFrom && <Alert kind="info">{loadedFrom} 일정으로 채웠어요. 날짜와 응답 마감은 일주일 뒤예요.</Alert>}
          {editId === null && lastEvent && !loadedFrom && (
            <Card className="space-y-3 border-brand-line bg-brand-soft">
              <div>
                <p className="text-sm font-bold text-ink">지난 일정과 같게 채우기</p>
                <p className="text-xs text-muted">날짜와 응답 마감은 일주일 뒤로 채워요. 채운 뒤 고칠 수 있어요.</p>
              </div>
              <div className="space-y-1 rounded-xl bg-surface px-3 py-2.5 text-sm">
                {lastEvent.title && <p className="font-semibold text-ink">{lastEvent.title}</p>}
                <p className="text-muted">{fmtEvent(lastEvent)}</p>
                {lastEvent.venue && <p className="text-muted">{lastEvent.venue}</p>}
                {lastEvent.memo && <p className="line-clamp-2 text-muted">{lastEvent.memo}</p>}
              </div>
              <Button variant="secondary" full className="text-sm" onClick={loadFromLast}>이 내용으로 채우기</Button>
            </Card>
          )}
          <Field label="제목 (선택)" value={f.title} onChange={set('title')} placeholder="일정 이름" hint="비워 두면 날짜로 보여요." />
          <div data-tutorial="FIRST_EVENT"><Field label="날짜" type="date" value={f.event_date} onChange={set('event_date')} required /></div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="시작" type="time" value={f.start_time} onChange={setStart} />
            <Field label="종료" type="time" value={f.end_time} onChange={setEnd} />
          </div>
          <Field label="장소" value={f.venue} onChange={set('venue')} placeholder="체육관 이름" />
          <div className="grid grid-cols-2 gap-3">
            <Field label="응답 마감 (선택)" type="date" value={f.rsvp_date} onChange={setRsvpDate} max={f.event_date || undefined} />
            <Field label="마감 시각" type="time" value={f.rsvp_time} onChange={set('rsvp_time')} disabled={!f.rsvp_date} />
          </div>
          <p className="-mt-2 px-1 text-xs text-muted">마감 뒤에는 팀원이 응답을 바꿀 수 없어요. 매니저는 대신 바꿀 수 있어요.</p>
          <Field label="메모 (선택)" value={f.memo} onChange={set('memo')} placeholder="회비, 준비물, 주차 안내 등" />
          {m.isError && <Alert>{errMsg(m.error, editId !== null ? '일정을 고치지 못했어요.' : '일정을 만들지 못했어요.')}</Alert>}
        </Content>
        <BottomAction><div data-tutorial="FIRST_EVENT"><Button type="submit" full loading={m.isPending} disabled={!f.event_date || (editId !== null && !prefilled)}>{editId !== null ? '고친 내용 저장' : '등록하고 응답 받기'}</Button></div></BottomAction>
      </form>
    </Screen>
  )
}

/** 응답 마감 시각을 "9/20 오후 10:00" 으로 */
function fmtDeadline(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' })}`
}

/* ---------- S-10 + S-11 일정 상세 ---------- */
export function EventDetailPage() {
  const { eventId } = useParams()
  const id = Number(eventId)
  const goBack = useGoBack()
  const nav = useNavigate()
  const qc = useQueryClient()
  const ev = useQuery({ queryKey: ['events', id], queryFn: () => eventsApi.get(id) })
  const att = useQuery({ queryKey: ['events', id, 'attendances'], queryFn: () => eventsApi.attendances(id) })
  const [sheet, setSheet] = useState<'new' | AttendanceView | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({ ABSENT: true })
  const [showAtt, setShowAtt] = useState(false)
  const refresh = () => invalidateEvent(qc, id, ev.data?.team_id)

  // 참석 응답은 누르는 즉시 바뀐 것처럼 보여 준다 (체육관 통신이 느려도). 실패하면 원래대로 돌린다
  const rsvpKey = ['rsvp', id]
  const respond = useMutation({
    mutationKey: rsvpKey,
    mutationFn: (status: 'ATTEND' | 'ABSENT') => eventsApi.respond(id, status),
    scope: { id: `rsvp-${id}` },  // 연달아 눌러도 순서대로 보낸다
    onMutate: async (status) => {
      setMsg(null)
      await qc.cancelQueries({ queryKey: ['events', id], exact: true })
      const prev = qc.getQueryData<EventView>(['events', id])
      if (prev) {
        const delta = (status === 'ATTEND' ? 1 : 0) - (prev.my_attendance === 'ATTEND' ? 1 : 0)
        qc.setQueryData<EventView>(['events', id], { ...prev, my_attendance: status, attend_count: prev.attend_count + delta })
      }
      return { prev }
    },
    onError: (e, _status, ctx) => {
      if (ctx?.prev) qc.setQueryData(['events', id], ctx.prev)
      toast(errMsg(e, '응답하지 못했어요.'), 'error')
    },
    // 연달아 누르면 아직 보낼 응답이 남아 있다(자기 자신도 센다) — 마지막 것만 다시 받아 화면이 번갈아 깜빡이지 않게
    onSettled: () => { if (qc.isMutating({ mutationKey: rsvpKey }) <= 1) refresh() },
  })
  // 지운 일정의 캐시는 화면을 떠난 뒤에 버린다 — 떠 있는 채로 지우면 이 화면이 빈 데이터로 다시 그려진다
  const deleted = useRef(false)
  useEffect(() => () => { if (deleted.current) qc.removeQueries({ queryKey: ['events', id] }) }, [qc, id])
  const remove = useMutation({
    mutationFn: () => eventsApi.remove(id),
    // 먼저 나가고 팀 일정 목록만 다시 받는다 (지운 일정 자체는 다시 부르지 않는다)
    onSuccess: () => { deleted.current = true; goBack('/'); qc.invalidateQueries({ queryKey: ev.data?.team_id ? ['events', 'team', ev.data.team_id] : ['events', 'team'] }) },
    onError: (e) => toast(errMsg(e, '일정을 지우지 못했어요.'), 'error'),
  })
  const closeRsvp = useMutation({ mutationFn: () => eventsApi.closeRsvp(id), onSuccess: refresh, onError: (e) => toast(errMsg(e, '마감하지 못했어요.'), 'error') })
  const removeGuest = useMutation({
    mutationFn: (pid: number) => eventsApi.removeGuest(id, pid),
    onSuccess: refresh,
    onError: (e) => toast(errMsg(e, '참석을 취소하지 못했어요.'), 'error'),
  })
  const setAtt = useMutation({
    mutationFn: ({ pid, status }: { pid: number; status: 'ATTEND' | 'ABSENT' }) => eventsApi.setAttendance(id, pid, status),
    onSuccess: refresh,
    onError: (e) => toast(errMsg(e, '참석 상태를 바꾸지 못했어요.'), 'error'),
  })

  if (ev.isLoading) return <Screen><TopBar title="일정" back="/" /><Spinner page /></Screen>
  if (!ev.data) return <Screen><TopBar title="일정" back="/" /><Content><LoadError message={errMsg(ev.error, '일정을 불러오지 못했어요.')} onRetry={() => ev.refetch()} retrying={ev.isFetching} /></Content></Screen>
  const e = ev.data
  const isManager = e.my_role === 'MANAGER'
  const past = e.survey_open || e.status === 'DONE'  // 종료 시각이 지났거나 기록까지 끝난 회차
  const started = e.status !== 'CANCELED' && new Date(`${e.event_date}T${e.start_time ?? '00:00:00'}`) <= new Date()  // 시작 시각 이후에만 쿼터 기록
  const s = att.data?.summary
  const groups = { ATTEND: [] as AttendanceView[], PENDING: [] as AttendanceView[], ABSENT: [] as AttendanceView[] }
  att.data?.items.forEach((i) => groups[i.status].push(i))
  const surveyBlock = isManager && e.survey_open && e.status !== 'CANCELED' && <SurveyProgressCard eventId={id} responded={e.survey_responded} total={e.survey_total} onMsg={setMsg} />
  const attend = s?.attend ?? e.attend_count
  const canAssign = !past && !e.adopted_candidate_id && e.quarter_count === 0
  // 매니저의 다음 할 일 하나 — 화면 아래에 고정한다 (경기 기록이 있으면 보기 · 고치기, 팀을 나누기 전이면 팀 나누기, 시작했으면 기록)
  const toQuarters = () => nav(`/events/${id}/quarters`)
  const action = !isManager || e.status === 'CANCELED' ? null
    : e.quarter_count > 0 ? { label: '경기 기록 보기 · 고치기', go: toQuarters, off: false }
    : canAssign ? { label: '팀 나누러 가기', go: () => nav(`/events/${id}/assign`), off: attend < 10 }
    : started ? { label: '경기 기록하기', go: toQuarters, off: false }
    : null
  // 팀원에게는 결과로 가는 한 줄 (매니저는 아래 고정 버튼)
  const quarterBlock = !isManager && e.quarter_count > 0 && (
    <button onClick={toQuarters} className="flex min-h-11 w-full items-center justify-between rounded-2xl border border-brand-line bg-brand-soft px-4 py-3 text-left text-sm font-semibold text-brand-ink">
      <span>경기 기록 {e.quarter_count}쿼터 · 결과 보기</span><span>→</span>
    </button>
  )

  // 참석 응답 · 요약 · 참석자 목록 (S-10 · S-11). 배정이 확정되면 매니저에게만, 접어서 보여 준다
  const attendanceBlock = (
    <>
        {/* RSVP 토글 (S-10) */}
        <div data-tutorial="FIRST_RSVP"><Card>
          <p className="mb-2 text-sm font-bold text-ink">{past ? '참석 응답' : e.rsvp_open ? '이번 일정, 참석하시나요?' : '참석 응답'}</p>
          <div className="grid grid-cols-2 gap-2">
            {(['ATTEND', 'ABSENT'] as const).map((st) => {
              const on = e.my_attendance === st
              return (
                <button
                  key={st}
                  disabled={!e.rsvp_open}
                  aria-pressed={on}
                  onClick={() => { if (!on) respond.mutate(st) }}
                  className={`min-h-12 rounded-xl border-2 text-[15px] font-bold transition disabled:opacity-50 ${
                    on ? (st === 'ATTEND' ? 'border-brand bg-brand text-on-brand' : 'border-inverse bg-inverse text-on-inverse') : 'border-line bg-surface text-muted'
                  }`}
                >
                  {st === 'ATTEND' ? '참석' : '불참'}
                </button>
              )
            })}
          </div>
          {isManager && e.rsvp_open && (
            <div className="mt-1 flex justify-end">
              <button
                onClick={async () => { if (await confirm(CLOSE_RSVP_CONFIRM)) closeRsvp.mutate() }}
                disabled={closeRsvp.isPending}
                className="-mr-2 min-h-11 px-2 text-xs font-semibold text-ink-2 disabled:opacity-50"
              >
                응답 미리 마감하기
              </button>
            </div>
          )}
          {!e.rsvp_open && <p className="mt-2 text-xs text-muted">{e.status === 'OPEN' && !past ? '응답이 마감됐어요.' : '응답 기한이 지난 일정이에요.'}</p>}
          {e.status !== 'CANCELED' && e.rsvp_open && !past && (
            <button onClick={() => setSheet('new')} className="mt-3 flex min-h-11 w-full items-center justify-between rounded-xl bg-brand-soft px-4 py-3 text-sm font-semibold text-brand-ink">
              + 게스트로 초대할 사람이 있어요 <span>→</span>
            </button>
          )}
        </Card></div>

        {/* 요약 (S-11) */}
        {s && (
          <Card>
            <div className="grid grid-cols-3 text-center">
              {[['참석', s.attend, 'text-brand-ink'], ['미응답', s.pending, 'text-muted'], ['불참', s.absent, 'text-faint']].map(([k, v, c]) => (
                <div key={String(k)}><p className={`text-2xl font-black ${c}`}>{v}</p><p className="text-[11px] text-muted">{k}</p></div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {POSITIONS.map((p) => (
                <span key={p} className={`rounded-md px-2 py-0.5 text-xs font-semibold ${s.position_counts[p] ? 'bg-info-soft text-ink-2' : 'bg-sunken text-faint'}`}>{p} {s.position_counts[p]}</span>
              ))}
            </div>
            {s.warnings.map((w) => <p key={w} className="mt-2 text-xs text-warn-ink">주의 · {w}</p>)}
          </Card>
        )}

        {/* 시작했지만 팀을 나누지 않은 날 — 아래 고정 버튼은 팀 나누기라, 나누지 않고 기록할 길을 따로 둔다 */}
        {isManager && canAssign && started && (
          <button onClick={toQuarters} className="min-h-11 w-full text-sm font-semibold text-ink-2 underline underline-offset-2">팀을 나누지 않고 경기 기록하기</button>
        )}

        {att.isLoading ? <Spinner /> : (
          (['ATTEND', 'PENDING', 'ABSENT'] as const).map((st) => groups[st].length > 0 && (
            <section key={st}>
              <button onClick={() => setCollapsed((c) => ({ ...c, [st]: !c[st] }))} aria-expanded={!collapsed[st]} className="mb-1 flex min-h-11 w-full items-center justify-between px-1">
                <span className="text-sm font-bold tracking-wide text-muted">{{ ATTEND: '참석', PENDING: '미응답', ABSENT: '불참' }[st]} {groups[st].length}</span>
                <span className="text-xs text-faint">{collapsed[st] ? '펼치기 ▾' : '접기 ▴'}</span>
              </button>
              <div className={`space-y-2 ${collapsed[st] ? 'hidden' : ''}`}>
                {groups[st].map((a) => (
                  <AttendeeRow
                    key={a.player.id}
                    a={a}
                    isMe={a.player.id === att.data?.my_player_id}
                    onEdit={() => setSheet(a)}
                    onRemove={async () => { if (await confirm({ title: `${a.player.display_name}님의 참석을 취소할까요?`, body: '게스트 기록은 남아서 다음에 다시 불러올 수 있어요.', confirmLabel: '참석 취소', danger: true })) removeGuest.mutate(a.player.id) }}
                    onSetStatus={isManager && a.player.kind === 'MEMBER' ? (status) => setAtt.mutate({ pid: a.player.id, status }) : undefined}
                    showGrade={isManager}
                  />
                ))}
              </div>
            </section>
          ))
        )}
    </>
  )

  return (
    <Screen>
      {/* 경기 기록이 있는(DONE) 일정은 실력 지표의 근거라 지울 수 없다. 배정을 확정한 일정(CLOSED)은 지울 수 있다 */}
      <TopBar tone="navy" title={e.title ?? fmtEvent(e)} back={`/teams/${e.team_id}`} right={isManager && (e.status === 'OPEN' || e.status === 'CLOSED') && (
        <span className="-mr-1 flex text-sm">
          <button className="min-h-11 min-w-11 px-2 font-semibold text-bar-ink" onClick={() => nav(`/events/${id}/edit`)}>고치기</button>
          <button
            className="min-h-11 min-w-11 px-2 font-semibold text-bar-sub disabled:opacity-50" disabled={remove.isPending}
            onClick={async () => { if (await confirm({ title: '일정을 지울까요?', body: '참석 응답과 팀 배정도 함께 지워지고 되돌릴 수 없어요.', confirmLabel: '일정 지우기', danger: true })) remove.mutate() }}
          >
            지우기
          </button>
        </span>
      )} />
      <div className="bg-bar px-4 pb-4 text-bar-ink">
        {/* 제목이 없으면 위 제목 줄이 이미 날짜다 */}
        {e.title && <p className="text-lg font-bold">{fmtEvent(e)}</p>}
        <p className="text-sm text-bar-sub">{e.venue ?? '장소 미정'}{e.memo ? ` · ${e.memo}` : ''}</p>
        <div className="mt-2 flex items-center gap-2 text-sm">
          <Badge tone={e.status === 'OPEN' ? 'success' : 'neutral'}>{{ OPEN: past ? '종료' : '응답 받는 중', CLOSED: past ? '종료' : '응답 마감', DONE: '기록 완료', CANCELED: '취소됨' }[e.status]}</Badge>
          <span className="text-bar-sub">참석 {e.attend_count}명</span>
          {e.rsvp_deadline && <span className="ml-auto text-xs text-bar-sub">마감 {fmtDeadline(e.rsvp_deadline)}</span>}
        </div>
      </div>

      <Content>
        {msg && <Alert>{msg}</Alert>}

        {/* 끝난 일정의 매니저 도구는 맨 위로: 경기 후 투표 독려 (경기 기록은 아래 고정 버튼) */}
        {isManager && past && surveyBlock}

        {e.adopted_candidate_id ? (
          <>
            {/* 배정이 확정되면 이 화면이 곧 팀 배정 결과다 — 팀 배정(설명 포함) → 이 팀에 맞는 전술 */}
            <AdoptedSection event={e} />
            {isManager && s && !past && (
              e.quarter_count > 0 ? (
                // 경기 기록이 붙은 배정은 바꿀 수 없다 (서버 422 ASSIGNMENT_LOCKED)
                <p className="rounded-xl bg-surface-2 px-3 py-2 text-xs text-muted">경기 기록이 있는 일정은 팀을 다시 나눌 수 없어요. 경기 기록을 먼저 지워 주세요.</p>
              ) : (
                <Button variant="secondary" full onClick={() => nav(`/events/${id}/assign`)}>팀 다시 나누기</Button>
              )
            )}
            <EventTactics event={e} />
            {!(isManager && past) && surveyBlock}
            {quarterBlock}
            {/* 참석 현황은 매니저만 — 팀원에게는 누가 불참했는지 보여 줄 필요가 없다 */}
            {isManager && (
              <section className="space-y-3">
                <button onClick={() => setShowAtt(!showAtt)} className="flex w-full items-center justify-between rounded-2xl border border-line bg-surface px-4 py-3 text-left" aria-expanded={showAtt}>
                  <span className="text-sm font-semibold text-ink">참석 현황 · 관리 <span className="font-normal text-muted">참석 {e.attend_count}명</span></span>
                  <span className="text-xs text-faint">{showAtt ? '접기 ▴' : '펼치기 ▾'}</span>
                </button>
                {showAtt && attendanceBlock}
              </section>
            )}
          </>
        ) : (
          <>
            {attendanceBlock}
            {/* 경기 후 투표 진입은 팀 화면의 일정 배너에서만 (사용자 결정). 여기서는 매니저 독려 카드만 */}
            {!(isManager && past) && surveyBlock}
            {quarterBlock}
          </>
        )}
      </Content>

      {action && (
        <BottomAction>
          {action.off && <p className="mb-2 text-center text-xs text-muted">참석 10명부터 나눌 수 있어요 · 지금 {attend}명</p>}
          <Button full disabled={action.off} onClick={action.go}>{action.label}</Button>
        </BottomAction>
      )}

      {sheet && (
        <GuestSheet
          eventId={id}
          editing={sheet === 'new' ? null : sheet}
          onClose={() => setSheet(null)}
          onDone={() => { setSheet(null); refresh() }}
          showGrade={isManager}
        />
      )}
    </Screen>
  )
}

/** 매니저 뷰 — "경기 후 투표 현황 N/M명 응답" + 독려 메시지 공유. 자동 발송은 없다 (스펙 3.3절) */
function SurveyProgressCard({ eventId, responded, total, onMsg }: { eventId: number; responded: number; total: number; onMsg: (m: string | null) => void }) {
  const share = useMutation({
    mutationFn: () => peerApi.shareMessage(eventId),
    onSuccess: async (m) => {
      // 카카오톡 → OS 공유 시트 → 클립보드 순 (lib/kakao). 링크는 서버가 준 투표 주소. 결과는 다른 공유와 같이 토스트로
      announceShare(await shareText(m.text.replace(m.link, '').trim(), m.link))
    },
    onError: (e) => onMsg(errMsg(e, '메시지를 만들지 못했어요.')),
  })
  const pct = total ? Math.round((responded / total) * 100) : 0
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-ink">경기 후 투표 현황</p>
          <p className="text-xs text-muted">{responded}/{total}명 응답 · 팀원 참석자 기준</p>
        </div>
        <Button variant="secondary" className="px-3 text-sm" loading={share.isPending} onClick={() => share.mutate()}>독려 메시지 공유</Button>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full rounded-full bg-brand transition-all" style={{ width: `${pct}%` }} /></div>
    </Card>
  )
}

function AttendeeRow({ a, isMe, onEdit, onRemove, onSetStatus, showGrade }: { a: AttendanceView; isMe: boolean; onEdit: () => void; onRemove: () => void; onSetStatus?: (s: 'ATTEND' | 'ABSENT') => void; showGrade: boolean }) {
  const p = a.player
  const guest = p.kind === 'GUEST'
  return (
    <Card className="flex items-center gap-3 py-3">
      <Avatar name={p.display_name} src={p.profile_image_url} />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 truncate font-semibold text-ink">
          {p.display_name}
          {isMe && <span className="text-[11px] text-brand-ink">(나)</span>}
          {guest && <Badge>게스트</Badge>}
          {guest && p.skill_confidence !== null && Number(p.skill_confidence) === 0 && <Badge tone="warn">?</Badge>}
        </p>
        <p className="truncate text-xs text-muted">
          {p.primary_position ?? (p.playable_positions[0] ?? '포지션 미입력')}
          {guest && a.registered_by_name && <span> · {a.registered_by_name} 초대</span>}
          {a.team_lock_request_player_name && <span className="text-brand-ink"> · 같은 팀 희망</span>}
          {a.note && <span> · {a.note}</span>}
        </p>
      </div>
      {showGrade && <GradeDot grade={p.skill_grade} />}
      {guest && a.can_edit ? (
        <div className="-my-1 -mr-1 flex shrink-0 items-center">
          <button onClick={onEdit} aria-label={`${p.display_name} 고치기`} className="flex min-h-11 min-w-11 items-center justify-center px-1">
            <span className="rounded-lg border border-line px-2 py-1 text-[11px] font-semibold text-ink-2">고치기</span>
          </button>
          <button onClick={onRemove} aria-label={`${p.display_name} 참석 취소`} className="flex min-h-11 min-w-11 items-center justify-center px-1 text-[11px] font-semibold text-danger-ink">참석 취소</button>
        </div>
      ) : onSetStatus ? (
        <button onClick={() => onSetStatus(a.status === 'ATTEND' ? 'ABSENT' : 'ATTEND')} className="-my-1 -mr-1 flex min-h-11 shrink-0 items-center px-1">
          <span className="rounded-lg border border-line px-2 py-1 text-[11px] font-semibold text-ink-2">{a.status === 'ATTEND' ? '불참 처리' : '참석 처리'}</span>
        </button>
      ) : null}
    </Card>
  )
}

/* ---------- 게스트 등록/수정 바텀시트 (S-10 · S-11 공용) ---------- */
function GuestSheet({ eventId, editing, onClose, onDone, showGrade }: { eventId: number; editing: AttendanceView | null; onClose: () => void; onDone: () => void; showGrade: boolean }) {
  const [name, setName] = useState(editing?.player.display_name ?? '')
  const [gradeValue, setGradeState] = useState<number | null>(null)
  const [gradeTouched, setGradeTouched] = useState(false)  // 고칠 때 등급을 건드렸을 때만 보낸다 (null = 미지정으로 되돌리기)
  const setGrade = (g: number | null) => { setGradeState(g); setGradeTouched(true) }
  const [height, setHeight] = useState<string>(editing?.player.height_cm ? String(editing.player.height_cm) : '')
  const [pref, setPref] = useState<Position | null>(editing?.player.primary_position ?? null)
  const [playable, setPlayable] = useState<Position[]>(editing?.player.playable_positions ?? [])
  const [lock, setLock] = useState<boolean>(editing ? editing.team_lock_request_player_id !== null : true)
  const [similar, setSimilar] = useState<PlayerCard[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reuseId, setReuseId] = useState<number | undefined>(undefined) // 불러온 이전 게스트의 레코드 id
  const presets = useQuery({ queryKey: ['events', eventId, 'guest-presets'], queryFn: () => eventsApi.presets(eventId) })
  // 고칠 때: 등급(1~5)은 카드에 실리지 않으므로 내가 초대했던 기록에서 채워 보여 준다. 건드리지 않으면 보내지 않는다
  const presetGrade = editing ? presets.data?.items.find((x) => x.existing_player_id === editing.player.id)?.skill_grade ?? null : null
  const grade = gradeTouched || !editing ? gradeValue : (presetGrade ?? gradeValue)

  const applyPreset = (pr: GuestPreset) => {
    setName(pr.display_name); setGradeState(pr.skill_grade); setHeight(pr.height_cm ? String(pr.height_cm) : ''); setPref(pr.preferred_position); setPlayable(pr.playable_positions); setLock(pr.team_lock_request)
    setReuseId(pr.existing_player_id ?? undefined)
  }

  const create = useMutation({
    mutationFn: (extra: Partial<EventGuestInput>) =>
      eventsApi.registerGuest(eventId, { display_name: name.trim(), skill_grade: grade, height_cm: height ? Number(height) : null, preferred_position: pref, playable_positions: playable, team_lock_request: lock, ...(reuseId ? { existing_player_id: reuseId } : {}), ...extra }),
    onSuccess: (r) => (r.kind === 'similar' ? setSimilar(r.similar) : onDone()),
    onError: (e) => setError(errMsg(e, '등록하지 못했어요.')),
  })
  const update = useMutation({
    mutationFn: () => {
      const patch: EventGuestUpdate = { display_name: name.trim(), preferred_position: pref, playable_positions: playable, team_lock_request: lock }
      if (gradeTouched) patch.skill_grade = grade
      const h = height ? Number(height) : null
      if (h !== (editing!.player.height_cm ?? null)) patch.height_cm = h  // 칸을 비우면 null 로 보내 키를 지운다
      return eventsApi.updateGuest(eventId, editing!.player.id, patch)
    },
    onSuccess: onDone,
    onError: (e) => setError(errMsg(e, '고치지 못했어요.')),
  })
  const busy = create.isPending || update.isPending

  return (
    <Sheet label={editing ? '게스트 고치기' : '게스트 초대'} title={editing ? '게스트 고치기' : '게스트 초대'} onClose={onClose}>
        <p className="mb-4 text-xs text-muted">이름만 있으면 돼요. 실력을 알면 등급까지 넣어 주세요.</p>
        {!editing && !similar && presets.data && presets.data.items.length > 0 && (
          <div className="mb-4">
            <p className="mb-1.5 text-sm font-medium text-ink">이전에 초대한 사람 불러오기</p>
            <div className="flex flex-wrap gap-1.5">
              {presets.data.items.map((pr) => (
                <button key={pr.id} type="button" onClick={() => applyPreset(pr)} aria-pressed={name === pr.display_name} className={`min-h-11 rounded-full border px-3 text-sm ${name === pr.display_name ? 'border-inverse bg-inverse font-semibold text-on-inverse' : 'border-line bg-surface text-ink'}`}>
                  {pr.display_name}{pr.skill_grade ? ` · ${pr.skill_grade}` : ''}{pr.preferred_position ? ` · ${pr.preferred_position}` : ''}
                </button>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-muted">고르면 지난번 정보를 그대로 채워요.</p>
          </div>
        )}

        {similar ? (
          <div className="space-y-2">
            <Alert kind="info">같은 이름의 게스트가 이미 있어요. 지난번에 온 분이면 골라 주세요.</Alert>
            {/* 보내는 동안은 다시 눌러도 무시 — 같은 게스트가 두 번 등록되지 않게 */}
            {similar.map((p) => (
              <Card key={p.id} onClick={() => { if (!busy) create.mutate({ existing_player_id: p.id }) }} className={`flex items-center gap-3 py-3 ${busy ? 'opacity-50' : ''}`}>
                <Avatar name={p.display_name} src={p.profile_image_url} />
                <div className="flex-1"><p className="font-semibold text-ink">{p.display_name}</p><p className="text-xs text-muted">{p.playable_positions.join(' · ') || '포지션 미입력'}</p></div>
                {showGrade && <GradeDot grade={p.skill_grade} />}
              </Card>
            ))}
            <Button variant="ghost" full onClick={() => create.mutate({ force_new: true })} loading={busy}>다른 사람이에요 — 새 게스트로 추가</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <Field label="이름" value={name} onChange={(e) => { setName(e.target.value); setReuseId(undefined) }} placeholder="게스트 이름을 입력해 주세요" maxLength={50} autoFocus />
            <Field label="키 (cm, 선택)" type="text" inputMode="numeric" value={height} onChange={(e) => setHeight(e.target.value.replace(/\D/g, '').slice(0, 3))} placeholder="키를 입력해 주세요" hint="팀 평균 키를 계산할 때만 써요." />
            <div>
              <p className="mb-1.5 text-sm font-medium text-ink">대략적인 실력 <span className="text-faint">(선택)</span></p>
              <div className="grid grid-cols-5 gap-1.5">
                {[1, 2, 3, 4, 5].map((g) => (
                  <button key={g} type="button" onClick={() => setGrade(grade === g ? null : g)} aria-pressed={grade === g} className={`min-h-11 rounded-xl border text-sm font-bold ${grade === g ? 'border-inverse bg-inverse text-on-inverse' : 'border-line bg-surface text-ink'}`}>{g}</button>
                ))}
              </div>
              <p className={`mt-1 text-[11px] ${grade === null ? 'text-warn-ink' : 'text-muted'}`}>
                {grade === null
                  ? '비워 두면 팀 평균으로 계산해요. 대략이라도 고르면 팀을 더 고르게 나눌 수 있어요 (1 초보 … 5 최상위).'
                  : '1 초보 … 5 우리 팀 최상위. 나중에 바꿀 수 있어요.'}
              </p>
            </div>
            <div>
              <p className="mb-1.5 text-sm font-medium text-ink">선호 포지션 <span className="text-faint">(선택)</span></p>
              <PosChips value={pref ? [pref] : []} onChange={(v) => { const np = v[v.length - 1] ?? null; setPref(np); if (np && !playable.includes(np)) setPlayable([...playable, np]) }} single />
            </div>
            <div>
              <p className="mb-1.5 text-sm font-medium text-ink">가능 포지션 <span className="text-faint">(선택)</span></p>
              <PosChips value={playable} onChange={setPlayable} />
            </div>
            <label className="flex items-center justify-between rounded-xl bg-surface-2 px-4 py-3">
              <span className="text-sm font-medium text-ink">나와 같은 팀으로 묶어 주세요<br /><span className="text-[11px] font-normal text-muted">매니저에게 제안으로 알려요</span></span>
              <input type="checkbox" checked={lock} onChange={(e) => setLock(e.target.checked)} className="size-5 accent-brand" />
            </label>
            {error && <Alert>{error}</Alert>}
            <Button full loading={busy} disabled={!name.trim()} onClick={() => (editing ? update.mutate() : create.mutate({}))}>
              {editing ? '저장' : '참석자에 추가'}
            </Button>
          </div>
        )}
    </Sheet>
  )
}

export function PosChips({ value, onChange, single }: { value: Position[]; onChange: (v: Position[]) => void; single?: boolean }) {
  return (
    <div className="flex gap-1.5">
      {POSITIONS.map((p) => {
        const on = value.includes(p)
        return (
          <button
            key={p}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== p) : single ? [p] : [...value, p])}
            className={`min-h-11 flex-1 rounded-lg border text-sm font-bold ${on ? 'border-inverse bg-inverse text-on-inverse' : 'border-line bg-surface text-ink'}`}
          >
            {p}
          </button>
        )
      })}
    </div>
  )
}
