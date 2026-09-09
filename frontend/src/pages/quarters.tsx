/**
 * S-15 쿼터 기록 (F8). 설계서 2.4절·2.5절: 기록은 매니저가 **활동이 끝난 뒤** 한 번에 입력한다.
 *
 * - 쿼터 카드 세로 누적형: 카드마다 스코어 스테퍼 2개 + 사이드별 출전 5명 체크 그리드 + 쿼터 길이.
 * - 출전 후보: 확정된 배정이 있으면 블랙/화이트 팀원이 각 사이드의 기본 후보, 없으면 참석자 전원을 양쪽에 보여준다.
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
import type { PlayerCard, QuarterIn, Side } from '../api/types'
import { Alert, Badge, Button, Card, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar, useGoBack } from '../components/layout'

type Draft = { quarter_no: number; black_score: number; white_score: number; duration_min: number; black: number[]; white: number[] }

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? `${e.message}${e.details.length ? ' ' + e.details.map((d) => d.reason).join(' ') : ''}` : fallback)
const draftKey = (eventId: number) => `quarters-draft-${eventId}`

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
  const [msg, setMsg] = useState<string | null>(null)
  const [restored, setRestored] = useState(false)

  const isManager = ev.data?.my_role === 'MANAGER'

  // 사이드별 후보: 확정 배정 팀원 우선, 없으면 참석자 전원
  const candidates = useMemo(() => {
    const attendees = (att.data?.items ?? []).filter((a) => a.status === 'ATTEND').map((a) => a.player)
    const byId = new Map<number, PlayerCard>(attendees.map((p) => [p.id, p]))
    saved.data?.items.forEach((q) => q.lineups.forEach((l) => { if (!byId.has(l.player_id)) byId.set(l.player_id, { id: l.player_id, display_name: l.display_name, kind: 'MEMBER', role: 'PLAYER', user_id: null, profile_image_url: null, skill_grade: null, primary_position: l.position, playable_positions: [], attendance_rate: null, skill_confidence: null, height_cm: null }) }))
    const black = adopted.data?.squads.find((s) => s.squad_no === 1)?.members ?? []
    const white = adopted.data?.squads.find((s) => s.squad_no === 2)?.members ?? []
    const all = [...byId.values()].sort((a, b) => a.display_name.localeCompare(b.display_name, 'ko'))
    return {
      black: black.length ? black : all,
      white: white.length ? white : all,
      hasAssignment: black.length > 0,
      nameOf: (pid: number) => byId.get(pid)?.display_name ?? [...black, ...white].find((m) => m.id === pid)?.display_name ?? `#${pid}`,
    }
  }, [att.data, adopted.data, saved.data])

  // 초기값: 서버 기록 > 로컬 임시 저장 > 빈 쿼터 1개 (배정 팀원 5명씩 미리 체크)
  useEffect(() => {
    if (quarters || saved.isLoading || adopted.isLoading) return
    if (saved.data && saved.data.items.length > 0) {
      setQuarters(saved.data.items.map((q) => ({ quarter_no: q.quarter_no, black_score: q.black_score, white_score: q.white_score, duration_min: q.duration_min, black: q.lineups.filter((l) => l.side === 'BLACK').map((l) => l.player_id), white: q.lineups.filter((l) => l.side === 'WHITE').map((l) => l.player_id) })))
      return
    }
    try {
      const raw = localStorage.getItem(draftKey(id))
      if (raw) { setQuarters(JSON.parse(raw) as Draft[]); setRestored(true); return }
    } catch { /* 저장소 없음 */ }
    const b = candidates.hasAssignment ? candidates.black.slice(0, 5).map((m) => m.id) : []
    const w = candidates.hasAssignment ? candidates.white.slice(0, 5).map((m) => m.id) : []
    setQuarters([{ quarter_no: 1, black_score: 0, white_score: 0, duration_min: 10, black: b, white: w }])
  }, [quarters, saved.data, saved.isLoading, adopted.isLoading, candidates, id])

  // 임시 저장
  useEffect(() => {
    if (!quarters || !isManager) return
    try { localStorage.setItem(draftKey(id), JSON.stringify(quarters)) } catch { /* ignore */ }
  }, [quarters, id, isManager])

  const save = useMutation({
    mutationFn: () => {
      const payload: QuarterIn[] = quarters!.map((q) => ({
        quarter_no: q.quarter_no, black_score: q.black_score, white_score: q.white_score, duration_min: q.duration_min,
        lineups: [...q.black.map((pid) => ({ player_id: pid, side: 'BLACK' as Side })), ...q.white.map((pid) => ({ player_id: pid, side: 'WHITE' as Side }))],
      }))
      return quartersApi.bulkSave(id, payload)
    },
    onSuccess: (r) => {
      try { localStorage.removeItem(draftKey(id)) } catch { /* ignore */ }
      qc.invalidateQueries({ queryKey: ['events'] }); qc.invalidateQueries({ queryKey: ['team'] }); qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['stats'] })
      setMsg(`저장했어요 (새로 ${r.created} · 수정 ${r.updated} · 삭제 ${r.deleted}). 실력 지표를 다시 계산했어요.`)
      goBack(`/events/${id}`)
    },
    onError: (e) => setMsg(errMsg(e, '저장하지 못했어요.')),
  })

  if (ev.isLoading || att.isLoading || saved.isLoading || !quarters) return <Screen><TopBar title="쿼터 기록" back={`/events/${id}`} /><Spinner /></Screen>
  if (!ev.data) return <Screen><TopBar title="쿼터 기록" back={`/events/${id}`} /><Content><Alert>일정을 불러오지 못했어요.</Alert></Content></Screen>
  const total = quarters.reduce((a, q) => ({ black: a.black + q.black_score, white: a.white + q.white_score }), { black: 0, white: 0 })
  const invalid = quarters.filter((q) => q.black.length !== 5 || q.white.length !== 5)
  const update = (i: number, patch: Partial<Draft>) => setQuarters((qs) => qs!.map((q, j) => (j === i ? { ...q, ...patch } : q)))
  const toggle = (i: number, side: 'black' | 'white', pid: number) =>
    setQuarters((qs) => qs!.map((q, j) => {
      if (j !== i) return q
      const list = q[side]
      const other = side === 'black' ? q.white : q.black
      if (other.includes(pid)) return q  // 같은 쿼터에 양 팀으로 동시에 뛸 수 없다
      return { ...q, [side]: list.includes(pid) ? list.filter((x) => x !== pid) : [...list, pid] }
    }))
  const addQuarter = () => setQuarters((qs) => { const last = qs![qs!.length - 1]; return [...qs!, { quarter_no: (last?.quarter_no ?? 0) + 1, black_score: 0, white_score: 0, duration_min: last?.duration_min ?? 10, black: last?.black ?? [], white: last?.white ?? [] }] })
  const removeQuarter = (i: number) => setQuarters((qs) => qs!.filter((_, j) => j !== i).map((q, j) => ({ ...q, quarter_no: j + 1 })))

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
                  <div className="flex items-center justify-between"><p className="font-bold text-navy-900">{q.quarter_no}쿼터</p><p className="text-sm font-bold"><span className="text-navy-900">{q.black_score}</span> : <span className="text-stone-600">{q.white_score}</span></p></div>
                  <p className="text-xs text-stone-600"><b>블랙</b> {q.lineups.filter((l) => l.side === 'BLACK').map((l) => l.display_name).join(' · ')}</p>
                  <p className="text-xs text-stone-600"><b>화이트</b> {q.lineups.filter((l) => l.side === 'WHITE').map((l) => l.display_name).join(' · ')}</p>
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
      <TopBar title="쿼터 기록" back={`/events/${id}`} right={<span className="mr-2 text-sm font-bold"><span className="text-navy-900">블랙 {total.black}</span> <span className="text-stone-400">:</span> <span className="text-stone-600">{total.white} 화이트</span></span>} />
      <Content>
        <p className="px-1 text-xs text-stone-500">경기 후 한 번에 입력하세요. 저장 전 내용은 이 기기에 임시 보관돼요.</p>
        {restored && <Alert kind="info">저장하지 않은 입력을 되살렸어요.</Alert>}
        {!candidates.hasAssignment && <Alert kind="warn">확정된 팀 배정이 없어 참석자 전원이 양쪽 후보로 보여요. 사이드별로 5명씩 골라 주세요.</Alert>}
        {msg && <Alert>{msg}</Alert>}
        {quarters.map((q, i) => (
          <Card key={i} className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-bold text-navy-900">{q.quarter_no}쿼터
                <label className="ml-2 text-xs font-normal text-stone-500">
                  <input type="number" min={1} max={60} value={q.duration_min} onChange={(ev2) => update(i, { duration_min: Math.max(1, Math.min(60, Number(ev2.target.value) || 10)) })} className="w-10 rounded border border-stone-200 px-1 text-center" />분
                </label>
              </p>
              {quarters.length > 1 && <button className="text-xs text-rose-500" onClick={() => removeQuarter(i)}>삭제</button>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Stepper label="블랙" dark value={q.black_score} onChange={(v) => update(i, { black_score: v })} />
              <Stepper label="화이트" value={q.white_score} onChange={(v) => update(i, { white_score: v })} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              {(['black', 'white'] as const).map((side) => {
                const list = q[side]
                const pool = side === 'black' ? candidates.black : candidates.white
                const ok = list.length === 5
                return (
                  <div key={side} className={`rounded-xl border p-2 ${side === 'black' ? 'border-team-black bg-team-black text-white' : 'border-stone-300 bg-team-white text-navy-900'}`}>
                    <p className={`mb-1 text-[11px] font-bold ${ok ? '' : 'text-rose-400'}`}>{side === 'black' ? '블랙' : '화이트'} 출전 {list.length}/5</p>
                    <div className="space-y-0.5">
                      {pool.map((p) => {
                        const on = list.includes(p.id)
                        const blocked = (side === 'black' ? q.white : q.black).includes(p.id)
                        return (
                          <label key={p.id} className={`flex items-center gap-2 rounded px-1 py-0.5 text-sm ${on ? (side === 'black' ? 'bg-court-500' : 'bg-court-100') : ''} ${blocked ? 'opacity-30' : ''}`}>
                            <input type="checkbox" checked={on} disabled={blocked} onChange={() => toggle(i, side, p.id)} className="accent-court-500" />
                            <span className="truncate">{p.display_name}</span>
                            {p.kind === 'GUEST' && <span className="text-[10px] opacity-60">G</span>}
                          </label>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>
        ))}
        <Button variant="ghost" full onClick={addQuarter}>+ 쿼터 추가 (직전 라인업 복사)</Button>
        {invalid.length > 0 && <Alert kind="warn">{invalid.map((q) => `${q.quarter_no}쿼터`).join(', ')}의 출전 인원이 5명이 아니에요.</Alert>}
        {saved.data && saved.data.summary.quarter_count > 0 && <PlayTime per={saved.data.summary.per_player} />}
      </Content>
      <BottomAction>
        <Button full loading={save.isPending} disabled={invalid.length > 0 || quarters.length === 0} onClick={() => save.mutate()}>
          {saved.data && saved.data.summary.quarter_count > 0 ? '기록 수정 저장' : '경기 후 일괄 저장'} ({quarters.length}쿼터)
        </Button>
      </BottomAction>
    </Screen>
  )
}

function Stepper({ label, dark, value, onChange }: { label: string; dark?: boolean; value: number; onChange: (v: number) => void }) {
  return (
    <div className={`rounded-xl p-2 ${dark ? 'bg-team-black text-white' : 'border border-stone-200 bg-team-white text-navy-900'}`}>
      <p className="text-[11px] font-semibold opacity-70">{label}</p>
      <div className="flex items-center justify-between">
        <button onClick={() => onChange(Math.max(0, value - 1))} className={`size-9 rounded-lg text-lg font-bold ${dark ? 'bg-white/10' : 'bg-stone-100'}`}>−</button>
        <input
          type="text" inputMode="numeric" pattern="[0-9]*" value={value}
          onChange={(e) => { const d = e.target.value.replace(/\D/g, '').slice(-2); onChange(d === '' ? 0 : Number(d)) }}  // 두 자리가 찬 뒤 더 치면 앞자리가 밀린다 (13 → 4 입력 → 34)
          onFocus={(e) => e.target.select()}
          className="w-14 bg-transparent text-center text-2xl font-black tabular-nums outline-none"
        />
        <button onClick={() => onChange(Math.min(99, value + 1))} className={`size-9 rounded-lg text-lg font-bold ${dark ? 'bg-court-500' : 'bg-court-100 text-court-700'}`}>+</button>
      </div>
    </div>
  )
}

export function ScoreBoard({ black, white, sub }: { black: number; white: number; sub?: string }) {
  return (
    <div className="flex items-center justify-center gap-4 rounded-2xl bg-navy-800 px-4 py-4 text-white">
      <div className="text-center"><p className="text-[11px] text-stone-300">블랙</p><p className="text-3xl font-black">{black}</p></div>
      <span className="text-xl text-navy-300">:</span>
      <div className="text-center"><p className="text-[11px] text-stone-300">화이트</p><p className="text-3xl font-black">{white}</p></div>
      {sub && <p className="ml-2 text-xs text-navy-200">{sub}</p>}
    </div>
  )
}

function PlayTime({ per }: { per: { player_id: number; display_name: string; side: Side; quarters: number }[] }) {
  if (!per.length) return null
  return (
    <Card>
      <p className="mb-1 text-sm font-bold text-navy-900">출전 쿼터 수</p>
      <div className="grid grid-cols-2 gap-x-3 text-xs">
        {(['BLACK', 'WHITE'] as const).map((side) => (
          <div key={side}>
            <p className="mb-0.5 font-semibold text-stone-500">{side === 'BLACK' ? '블랙' : '화이트'}</p>
            {per.filter((p) => p.side === side).map((p) => <p key={p.player_id} className="flex justify-between text-stone-700"><span>{p.display_name}</span><Badge>{p.quarters}</Badge></p>)}
          </div>
        ))}
      </div>
    </Card>
  )
}
