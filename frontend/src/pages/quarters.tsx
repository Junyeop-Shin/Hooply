/**
 * S-15 쿼터 기록 (F8). 설계서 2.4절·2.5절: 기록은 매니저가 **활동이 끝난 뒤** 한 번에 입력한다.
 *
 * - 쿼터 카드 세로 누적형: 카드마다 스코어 스테퍼 2개 + 사이드별 출전 5명 체크 그리드 + 쿼터 길이(기본 8분, 1~10분).
 * - 체크 그리드 순서: 그 팀에 배정된 사람이 맨 위, 그 아래에 **다른 팀 사람**(경기 중 팀을 옮긴 경우 여기서 바로 체크),
 *   카드 맨 아래에 두 팀 공통의 "새 멤버 추가" (늦게 온 회원 · 당일 처음 온 게스트). 잘못 넣은 사람도 그 패널에서 뺀다.
 *   별도의 명단 요약 섹션은 두지 않는다 — 확정 배정은 일정 화면에서 보고, 여기서는 체크 칸 자체가 명단이다.
 * - 출전 명단은 확정 배정을 기본값으로 삼되 그날 실제로 온 사람에 맞춰 고칠 수 있다 (2.5절 "인원이 매번 가변").
 *   어느 쿼터에 이미 체크된 사람은 그 사이드 명단에서 자동으로 유지된다 — 옮겨도 지난 쿼터 기록이 깨지지 않는다.
 * - "+ 쿼터 추가" 는 직전 쿼터의 라인업을 복사한다 (로테이션 1~2명만 바꾸면 되도록).
 * - 저장 전 입력은 localStorage 에 임시 저장한다 (5.4절 네트워크 오류 대비).
 * - 플레이어에게는 읽기 전용 결과 화면.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { assignmentsApi } from '../api/assignments'
import { eventsApi } from '../api/events'
import { quartersApi } from '../api/quarters'
import { teamsApi } from '../api/teams'
import type { PlayerCard, QuarterIn, Side } from '../api/types'
import { Alert, Badge, Button, Card, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar, useGoBack } from '../components/layout'
import { FirstTimeTip } from '../components/tutorial'

type Draft = { quarter_no: number; black_score: number; white_score: number; duration_min: number; black: number[]; white: number[] }
type SideKey = 'black' | 'white'
/** 확정 배정 밖에서 매니저가 명단에 넣은 사람 (그날 늦게 온 회원·게스트·팀을 옮긴 사람) */
type Extra = Record<SideKey, number[]>

/** 쿼터 길이 — 백엔드 app/schemas/game.py 와 같은 값 */
const DEFAULT_DURATION = 8
const MIN_DURATION = 1
const MAX_DURATION = 10

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? `${e.message}${e.details.length ? ' ' + e.details.map((d) => d.reason).join(' ') : ''}` : fallback)
const draftKey = (eventId: number) => `quarters-draft-${eventId}`
const emptyExtra: Extra = { black: [], white: [] }
const uniq = (ids: number[]) => [...new Set(ids)]
const stub = (id: number, name: string): PlayerCard => ({
  id, user_id: null, kind: 'MEMBER', display_name: name, role: 'PLAYER', profile_image_url: null,
  skill_grade: null, primary_position: null, playable_positions: [], attendance_rate: null, skill_confidence: null, height_cm: null,
})

export function QuartersPage() {
  const { eventId } = useParams()
  const id = Number(eventId)
  const goBack = useGoBack()
  const qc = useQueryClient()
  const ev = useQuery({ queryKey: ['events', id], queryFn: () => eventsApi.get(id) })
  const att = useQuery({ queryKey: ['events', id, 'attendances'], queryFn: () => eventsApi.attendances(id) })
  const adopted = useQuery({ queryKey: ['events', id, 'adopted'], queryFn: () => assignmentsApi.adopted(id), retry: false })
  const saved = useQuery({ queryKey: ['events', id, 'quarters'], queryFn: () => quartersApi.list(id) })
  const [quarters, setQuarters] = useState<Draft[] | null>(null)
  const [extra, setExtra] = useState<Extra>(emptyExtra)
  const [msg, setMsg] = useState<string | null>(null)
  const [restored, setRestored] = useState(false)
  const [addFor, setAddFor] = useState<number | null>(null)  // 새 멤버 추가 패널이 열린 쿼터 카드 index

  const isManager = ev.data?.my_role === 'MANAGER'
  const teamId = ev.data?.team_id
  // 명단에 넣을 수 있는 사람 전체 — 팀 회원과 팀의 게스트 기록까지 (참석 응답을 안 한 사람도 포함)
  const members = useQuery({ queryKey: ['team', teamId, 'players'], queryFn: () => teamsApi.players(teamId!), enabled: !!teamId && !!isManager })
  const teamGuests = useQuery({ queryKey: ['team', teamId, 'guests'], queryFn: () => teamsApi.guests(teamId!), enabled: !!teamId && !!isManager })

  /** id → 카드. 참석자·팀 회원·게스트·확정 배정·이미 저장된 라인업을 모두 합친다 */
  const people = useMemo(() => {
    const byId = new Map<number, PlayerCard>()
    const put = (p: PlayerCard) => { if (!byId.has(p.id)) byId.set(p.id, p) }
    ;(att.data?.items ?? []).forEach((a) => put(a.player))
    adopted.data?.squads.forEach((s) => s.members.forEach(put))
    ;(members.data?.items ?? []).forEach(put)
    ;(teamGuests.data?.items ?? []).forEach(put)
    saved.data?.items.forEach((q) => q.lineups.forEach((l) => put(stub(l.player_id, l.display_name))))
    return byId
  }, [att.data, adopted.data, members.data, teamGuests.data, saved.data])

  const attendIds = useMemo(() => (att.data?.items ?? []).filter((a) => a.status === 'ATTEND').map((a) => a.player.id), [att.data])
  const squadIds = useMemo(() => ({
    black: adopted.data?.squads.find((s) => s.squad_no === 1)?.members.map((m) => m.id) ?? [],
    white: adopted.data?.squads.find((s) => s.squad_no === 2)?.members.map((m) => m.id) ?? [],
  }), [adopted.data])
  const hasAssignment = squadIds.black.length > 0

  /** 사이드별 출전 후보: 확정 배정(없으면 참석자 전원) + 이미 그 사이드로 기록된 사람 + 매니저가 추가한 사람 */
  const pool = useMemo(() => {
    const used = (side: SideKey) => (quarters ?? []).flatMap((q) => q[side])
    const build = (side: SideKey) => {
      const base = hasAssignment ? squadIds[side] : attendIds
      return uniq([...base, ...used(side), ...extra[side]]).map((pid) => people.get(pid) ?? stub(pid, `#${pid}`))
    }
    return { black: build('black'), white: build('white') }
  }, [quarters, extra, people, squadIds, attendIds, hasAssignment])

  const nameOf = (pid: number) => people.get(pid)?.display_name ?? `#${pid}`

  // 초기값: 서버 기록 > 로컬 임시 저장 > 빈 쿼터 1개 (배정 팀원 5명씩 미리 체크)
  useEffect(() => {
    if (quarters || saved.isLoading || adopted.isLoading) return
    if (saved.data && saved.data.items.length > 0) {
      setQuarters(saved.data.items.map((q) => ({ quarter_no: q.quarter_no, black_score: q.black_score, white_score: q.white_score, duration_min: q.duration_min, black: q.lineups.filter((l) => l.side === 'BLACK').map((l) => l.player_id), white: q.lineups.filter((l) => l.side === 'WHITE').map((l) => l.player_id) })))
      return
    }
    try {
      const raw = localStorage.getItem(draftKey(id))
      if (raw) {
        const parsed = JSON.parse(raw) as Draft[] | { quarters: Draft[]; extra?: Extra }
        const qs = Array.isArray(parsed) ? parsed : parsed.quarters  // 예전 형식(배열)도 읽는다
        if (qs?.length) {
          setQuarters(qs)
          if (!Array.isArray(parsed) && parsed.extra) setExtra({ black: parsed.extra.black ?? [], white: parsed.extra.white ?? [] })
          setRestored(true)
          return
        }
      }
    } catch { /* 저장소 없음 */ }
    const b = hasAssignment ? squadIds.black.slice(0, 5) : []
    const w = hasAssignment ? squadIds.white.slice(0, 5) : []
    setQuarters([{ quarter_no: 1, black_score: 0, white_score: 0, duration_min: DEFAULT_DURATION, black: b, white: w }])
  }, [quarters, saved.data, saved.isLoading, adopted.isLoading, hasAssignment, squadIds, id])

  // 임시 저장
  useEffect(() => {
    if (!quarters || !isManager) return
    try { localStorage.setItem(draftKey(id), JSON.stringify({ quarters, extra })) } catch { /* ignore */ }
  }, [quarters, extra, id, isManager])

  const save = useMutation({
    mutationFn: () => {
      const payload: QuarterIn[] = quarters!.map((q) => ({
        quarter_no: q.quarter_no, black_score: q.black_score, white_score: q.white_score, duration_min: q.duration_min,
        lineups: [...q.black.map((pid) => ({ player_id: pid, side: 'BLACK' as Side })), ...q.white.map((pid) => ({ player_id: pid, side: 'WHITE' as Side }))],
      }))
      return quartersApi.bulkSave(id, payload)
    },
    onSuccess: () => {
      try { localStorage.removeItem(draftKey(id)) } catch { /* ignore */ }
      qc.invalidateQueries({ queryKey: ['events'] }); qc.invalidateQueries({ queryKey: ['team'] }); qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['stats'] })
      setMsg(`저장했어요. 실력에 반영했어요.`)
      goBack(`/events/${id}`)
    },
    onError: (e) => setMsg(errMsg(e, '저장하지 못했어요.')),
  })

  if (ev.isLoading || att.isLoading || saved.isLoading || !quarters) return <Screen><TopBar title="경기 기록" back={`/events/${id}`} /><Spinner /></Screen>
  if (!ev.data) return <Screen><TopBar title="경기 기록" back={`/events/${id}`} /><Content><Alert>일정을 불러오지 못했어요.</Alert></Content></Screen>
  const total = quarters.reduce((a, q) => ({ black: a.black + q.black_score, white: a.white + q.white_score }), { black: 0, white: 0 })
  const invalid = quarters.filter((q) => q.black.length !== 5 || q.white.length !== 5)
  const update = (i: number, patch: Partial<Draft>) => setQuarters((qs) => qs!.map((q, j) => (j === i ? { ...q, ...patch } : q)))
  const toggle = (i: number, side: SideKey, pid: number) =>
    setQuarters((qs) => qs!.map((q, j) => {
      if (j !== i) return q
      const list = q[side]
      const other = side === 'black' ? q.white : q.black
      if (other.includes(pid)) return q  // 같은 쿼터에 양 팀으로 동시에 뛸 수 없다
      return { ...q, [side]: list.includes(pid) ? list.filter((x) => x !== pid) : [...list, pid] }
    }))
  const addQuarter = () => setQuarters((qs) => { const last = qs![qs!.length - 1]; return [...qs!, { quarter_no: (last?.quarter_no ?? 0) + 1, black_score: 0, white_score: 0, duration_min: last?.duration_min ?? DEFAULT_DURATION, black: last?.black ?? [], white: last?.white ?? [] }] })
  const removeQuarter = (i: number) => setQuarters((qs) => qs!.filter((_, j) => j !== i).map((q, j) => ({ ...q, quarter_no: j + 1 })))
  const addToSide = (side: SideKey, pid: number) => setExtra((e) => (e[side].includes(pid) ? e : { ...e, [side]: [...e[side], pid] }))
  const dropFromSide = (side: SideKey, pid: number) => setExtra((e) => ({ ...e, [side]: e[side].filter((x) => x !== pid) }))
  /** 어떤 쿼터에도 체크되지 않았고 확정 배정에도 없는 사람만 명단에서 뺄 수 있다 */
  const removable = (side: SideKey, pid: number) =>
    extra[side].includes(pid) && !quarters.some((q) => q[side].includes(pid))

  // ---- 플레이어: 읽기 전용 ----
  if (!isManager) {
    const s = saved.data?.summary
    return (
      <Screen>
        <TopBar title="경기 기록" back={`/events/${id}`} />
        <Content>
          {!s || s.quarter_count === 0 ? <Alert kind="info">아직 기록된 쿼터가 없어요.</Alert> : (
            <>
              <ScoreBoard black={s.black_total} white={s.white_total} sub={`${s.quarter_count}쿼터 · 블랙 ${s.black_wins}승 / 화이트 ${s.white_wins}승`} />
              {saved.data!.items.map((q) => (
                <Card key={q.id} className="space-y-1">
                  <div className="flex items-center justify-between"><p className="font-bold text-ink">{q.quarter_no}쿼터</p><p className="text-sm font-bold"><span className="text-ink">{q.black_score}</span> : <span className="text-muted">{q.white_score}</span></p></div>
                  <p className="text-xs text-muted"><b>블랙</b> {q.lineups.filter((l) => l.side === 'BLACK').map((l) => l.display_name).join(' · ')}</p>
                  <p className="text-xs text-muted"><b>화이트</b> {q.lineups.filter((l) => l.side === 'WHITE').map((l) => l.display_name).join(' · ')}</p>
                </Card>
              ))}
              <PlayTime per={s.per_player} />
            </>
          )}
        </Content>
      </Screen>
    )
  }

  // ---- 매니저: 입력 ----
  return (
    <Screen>
      <TopBar title="경기 기록" back={`/events/${id}`} right={<span className="mr-2 text-sm font-bold"><span className="text-ink">블랙 {total.black}</span> <span className="text-faint">:</span> <span className="text-muted">{total.white} 화이트</span></span>} />
      <Content>
        <FirstTimeTip id="quarters" />
        <p className="px-1 text-xs text-muted">경기 후 한 번에 입력하세요. 저장 전 내용은 이 기기에 임시 보관돼요.</p>
        {restored && <Alert kind="info">저장하지 않은 입력을 되살렸어요.</Alert>}
        {!hasAssignment && <Alert kind="warn">확정된 팀 배정이 없어 참석자 전원이 양쪽에 보여요. 팀마다 5명씩 골라 주세요.</Alert>}
        {msg && <Alert>{msg}</Alert>}

        {quarters.map((q, i) => (
          <Card key={q.quarter_no} className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-bold text-ink">{q.quarter_no}쿼터
                <label className="ml-2 text-xs font-normal text-muted">
                  <input
                    type="number" min={MIN_DURATION} max={MAX_DURATION} value={q.duration_min}
                    onChange={(ev2) => update(i, { duration_min: Math.max(MIN_DURATION, Math.min(MAX_DURATION, Number(ev2.target.value) || DEFAULT_DURATION)) })}
                    aria-label={`${q.quarter_no}쿼터 길이(분)`}
                    className="w-10 rounded border border-line px-1 text-center"
                  />분
                </label>
              </p>
              {quarters.length > 1 && <button className="text-xs text-danger-ink" onClick={() => removeQuarter(i)}>삭제</button>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Stepper label="블랙" dark value={q.black_score} onChange={(v) => update(i, { black_score: v })} />
              <Stepper label="화이트" value={q.white_score} onChange={(v) => update(i, { white_score: v })} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(['black', 'white'] as const).map((side) => {
                const list = q[side]
                const ok = list.length === 5
                const otherSide: SideKey = side === 'black' ? 'white' : 'black'
                const ownIds = new Set(pool[side].map((p) => p.id))
                const others = pool[otherSide].filter((p) => !ownIds.has(p.id))  // 팀을 옮긴 경우를 대비해 아래에 둔다
                const row = (p: PlayerCard, dim: boolean) => {
                  const on = list.includes(p.id)
                  const blocked = q[otherSide].includes(p.id)
                  return (
                    <label key={p.id} className={`flex items-center gap-2 rounded px-1 py-0.5 text-sm ${on ? (side === 'black' ? 'bg-court-500 text-white' : 'bg-court-100') : dim ? 'opacity-60' : ''} ${blocked ? 'opacity-30' : ''}`}>
                      <input type="checkbox" checked={on} disabled={blocked} onChange={() => toggle(i, side, p.id)} className="accent-brand" />
                      <span className="truncate">{p.display_name}</span>
                      {p.kind === 'GUEST' && <span className="text-[10px] opacity-60">G</span>}
                    </label>
                  )
                }
                return (
                  <div key={side} className={`rounded-xl border p-2 ${side === 'black' ? 'border-team-black bg-team-black text-team-black-ink [color-scheme:dark]' : 'border-line-strong bg-team-white text-team-white-ink [color-scheme:light]'}`}>
                    <p className={`mb-1 text-[11px] font-bold ${ok ? '' : 'text-rose-400'}`}>{side === 'black' ? '블랙' : '화이트'} 출전 {list.length}/5</p>
                    <div className="space-y-0.5" data-roster={`${side}-own`}>{pool[side].map((p) => row(p, false))}</div>
                    {others.length > 0 && (
                      <>
                        <p className="mb-0.5 mt-2 border-t border-current/20 pt-1.5 text-[10px] font-semibold opacity-60">다른 팀 · 옮겼으면 여기서 체크</p>
                        <div className="space-y-0.5" data-roster={`${side}-other`}>{others.map((p) => row(p, true))}</div>
                      </>
                    )}
                  </div>
                )
              })}
            </div>
            <button
              type="button" onClick={() => setAddFor((v) => (v === i ? null : i))}
              className="flex min-h-10 w-full items-center justify-center rounded-xl border border-dashed border-line-strong text-sm font-semibold text-ink-2"
            >
              {addFor === i ? '닫기' : '＋ 새 멤버 추가'}
            </button>
            {addFor === i && (
              <RosterEditor
                eventId={id} people={people} pool={pool} attendIds={attendIds}
                onAdd={addToSide} removable={removable} onRemove={dropFromSide}
                onError={(m) => setMsg(m)}
                onGuestAdded={() => { qc.invalidateQueries({ queryKey: ['events', id, 'attendances'] }); qc.invalidateQueries({ queryKey: ['team', teamId, 'guests'] }) }}
              />
            )}
          </Card>
        ))}
        <Button variant="ghost" full onClick={addQuarter}>+ 쿼터 추가 (앞 쿼터 명단 그대로)</Button>
        {invalid.length > 0 && <Alert kind="warn">{invalid.map((q) => `${q.quarter_no}쿼터`).join(', ')}의 출전 인원이 5명이 아니에요.</Alert>}
        {saved.data && saved.data.summary.quarter_count > 0 && <PlayTime per={saved.data.summary.per_player} />}
        <p className="px-1 text-[11px] text-faint">명단에 넣은 사람: {[...extra.black, ...extra.white].length ? uniq([...extra.black, ...extra.white]).map(nameOf).join(' · ') : '없음'}</p>
      </Content>
      <BottomAction>
        <Button full loading={save.isPending} disabled={invalid.length > 0 || quarters.length === 0} onClick={() => save.mutate()}>
          {saved.data && saved.data.summary.quarter_count > 0 ? '기록 수정 저장' : '경기 후 한 번에 저장'} ({quarters.length}쿼터)
        </Button>
      </BottomAction>
    </Screen>
  )
}

/** 새 멤버 추가 — 팀 회원·게스트를 어느 팀 명단에 넣을지 고르고, 당일 처음 온 게스트는 여기서 바로 등록한다. 두 팀 공통 */
function RosterEditor({
  eventId, people, pool, attendIds, onAdd, removable, onRemove, onError, onGuestAdded,
}: {
  eventId: number
  people: Map<number, PlayerCard>
  pool: Record<SideKey, PlayerCard[]>
  attendIds: number[]
  onAdd: (side: SideKey, pid: number) => void
  /** 매니저가 넣었고 아직 어느 쿼터에도 체크되지 않은 사람만 뺄 수 있다 */
  removable: (side: SideKey, pid: number) => boolean
  onRemove: (side: SideKey, pid: number) => void
  onError: (m: string) => void
  onGuestAdded: () => void
}) {
  const [q, setQ] = useState('')
  const [guestName, setGuestName] = useState('')
  const inBlack = new Set(pool.black.map((p) => p.id))
  const inWhite = new Set(pool.white.map((p) => p.id))
  const attend = new Set(attendIds)
  const rows = [...people.values()]
    .filter((p) => !inBlack.has(p.id) || !inWhite.has(p.id) || removable('black', p.id) || removable('white', p.id))
    .filter((p) => !q.trim() || p.display_name.includes(q.trim()))
    // 아직 어느 명단에도 없는 사람(늦게 온 회원·게스트)이 먼저, 그다음 참석 응답자, 그다음 이름순
    .sort((a, b) => Number(inBlack.has(b.id) || inWhite.has(b.id)) - Number(inBlack.has(a.id) || inWhite.has(a.id)) || Number(attend.has(b.id)) - Number(attend.has(a.id)) || a.display_name.localeCompare(b.display_name, 'ko'))
    .slice(0, 40)

  const addGuest = useMutation({
    mutationFn: async (side: SideKey) => {
      const res = await eventsApi.registerGuest(eventId, { display_name: guestName.trim(), force_new: true })
      if (res.kind !== 'registered') throw new Error('등록하지 못했어요.')
      return { side, player: res.view.player }
    },
    onSuccess: ({ side, player }) => { onAdd(side, player.id); setGuestName(''); onGuestAdded() },
    onError: (e) => onError(errMsg(e, '게스트를 등록하지 못했어요.')),
  })

  return (
    <div className="space-y-3 rounded-xl bg-surface-2 p-3">
      <p className="text-xs text-muted">넣으면 그 팀 명단에 올라와요. 출전은 위에서 체크하세요.</p>
      <div>
        <input
          value={q} onChange={(e) => setQ(e.target.value)} placeholder="이름으로 찾기" aria-label="명단에 넣을 사람 찾기"
          className="w-full rounded-xl border border-line px-3 py-2 text-sm"
        />
        <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
          {rows.map((p) => (
            <div key={p.id} className="flex items-center gap-2 text-sm">
              <span className="min-w-0 flex-1 truncate text-ink">
                {p.display_name}
                {p.kind === 'GUEST' && <Badge>게스트</Badge>}
                {!attend.has(p.id) && <span className="ml-1 text-[10px] text-faint">참석 응답 없음</span>}
              </span>
              {(['black', 'white'] as const).map((side) => {
                const already = side === 'black' ? inBlack.has(p.id) : inWhite.has(p.id)
                const canRemove = already && removable(side, p.id)
                return (
                  <button
                    key={side} disabled={already && !canRemove} onClick={() => (canRemove ? onRemove(side, p.id) : onAdd(side, p.id))}
                    aria-label={canRemove ? `${p.display_name} ${side === 'black' ? '블랙' : '화이트'} 명단에서 빼기` : undefined}
                    className={`min-h-8 rounded-lg px-2 text-xs font-semibold ${canRemove ? 'border border-danger-line text-danger-ink' : already ? 'bg-sunken text-faint' : side === 'black' ? 'bg-team-black text-team-black-ink' : 'border border-line-strong text-ink'}`}
                  >
                    {canRemove ? (side === 'black' ? '블랙 빼기' : '화이트 빼기') : already ? '있음' : side === 'black' ? '＋블랙' : '＋화이트'}
                  </button>
                )
              })}
            </div>
          ))}
          {rows.length === 0 && <p className="text-xs text-faint">넣을 수 있는 사람이 없어요.</p>}
        </div>
      </div>
      <div className="border-t border-line pt-3">
        <p className="mb-1 text-xs font-semibold text-ink">처음 온 게스트 추가</p>
        <div className="flex items-center gap-2">
          <input
            value={guestName} onChange={(e) => setGuestName(e.target.value)} placeholder="이름" aria-label="새 게스트 이름"
            className="min-w-0 flex-1 rounded-xl border border-line px-3 py-2 text-sm"
          />
          {(['black', 'white'] as const).map((side) => (
            <button
              key={side} disabled={!guestName.trim() || addGuest.isPending} onClick={() => addGuest.mutate(side)}
              className={`min-h-9 rounded-lg px-2 text-xs font-semibold disabled:opacity-40 ${side === 'black' ? 'bg-navy-900 text-white' : 'border border-line-strong text-ink'}`}
            >
              {side === 'black' ? '＋블랙' : '＋화이트'}
            </button>
          ))}
        </div>
        <p className="mt-1 text-[11px] text-faint">이 일정 참석자로도 함께 등록돼요. 실력 등급은 나중에 참석자 화면에서 지정할 수 있어요.</p>
      </div>
    </div>
  )
}

function Stepper({ label, dark, value, onChange }: { label: string; dark?: boolean; value: number; onChange: (v: number) => void }) {
  return (
    <div className={`rounded-xl p-2 ${dark ? 'bg-team-black text-team-black-ink' : 'border border-line-strong bg-team-white text-team-white-ink'}`}>
      <p className="text-[11px] font-semibold opacity-70">{label}</p>
      <div className="flex items-center justify-between">
        <button onClick={() => onChange(Math.max(0, value - 1))} className={`size-9 rounded-lg text-lg font-bold ${dark ? 'bg-white/10' : 'bg-stone-200'}`}>−</button>
        <input
          type="text" inputMode="numeric" pattern="[0-9]*" value={value} aria-label={`${label} 득점`}
          onChange={(e) => { const d = e.target.value.replace(/\D/g, '').slice(-2); onChange(d === '' ? 0 : Number(d)) }}  // 두 자리가 찬 뒤 더 치면 앞자리가 밀린다 (13 → 4 입력 → 34)
          onFocus={(e) => e.target.select()}
          className="w-14 bg-transparent text-center text-2xl font-black tabular-nums outline-none"
        />
        <button onClick={() => onChange(Math.min(99, value + 1))} className={`size-9 rounded-lg text-lg font-bold ${dark ? 'bg-court-500 text-white' : 'bg-court-100 text-court-700'}`}>+</button>
      </div>
    </div>
  )
}

export function ScoreBoard({ black, white, sub }: { black: number; white: number; sub?: string }) {
  return (
    <div className="flex items-center justify-center gap-4 rounded-2xl bg-bar px-4 py-4 text-bar-ink">
      <div className="text-center"><p className="text-[11px] text-bar-sub">블랙</p><p className="text-3xl font-black">{black}</p></div>
      <span className="text-xl text-bar-sub">:</span>
      <div className="text-center"><p className="text-[11px] text-bar-sub">화이트</p><p className="text-3xl font-black">{white}</p></div>
      {sub && <p className="ml-2 text-xs text-bar-sub">{sub}</p>}
    </div>
  )
}

function PlayTime({ per }: { per: { player_id: number; display_name: string; side: Side; quarters: number }[] }) {
  if (!per.length) return null
  return (
    <Card>
      <p className="mb-1 text-sm font-bold text-ink">출전 쿼터 수</p>
      <div className="grid grid-cols-2 gap-x-3 text-xs">
        {(['BLACK', 'WHITE'] as const).map((side) => (
          <div key={side}>
            <p className="mb-0.5 font-semibold text-muted">{side === 'BLACK' ? '블랙' : '화이트'}</p>
            {per.filter((p) => p.side === side).map((p) => <p key={p.player_id} className="flex justify-between text-ink-2"><span>{p.display_name}</span><Badge>{p.quarters}</Badge></p>)}
          </div>
        ))}
      </div>
    </Card>
  )
}
