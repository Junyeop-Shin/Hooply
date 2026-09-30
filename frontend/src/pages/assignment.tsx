/**
 * S-12 배정 실행 · S-13 배정 결과(매니저) · S-14 배정 결과(플레이어) — F5 · F6 · F7 · F15.
 *
 * 3팀(v1.7): 참석이 15명을 넘으면 "3팀으로 나누기" 체크 → 블랙 · 화이트 · 레드 세 칸. 결과에서는 한 명을 고른 뒤 옮길 팀을 고른다.
 *   18명이 넘는데 2팀이면 3팀을 권하는 안내만 붙인다 — 2팀도 그대로 짤 수 있다.
 * S-12: 대기 칸(참석자 칩) + 블랙/화이트(/레드) 팀 칸. 칩을 길게(여기서는 탭) 다중 선택 → 같은 팀으로 묶기 / 갈라놓기 /
 *       블랙·화이트에 사전 배치. 제약을 바꿀 때마다 프리플라이트(validate)로 실행 버튼을 잠근다 (FR-20).
 *       게스트의 "묶기 제안"은 배지로 보이고 승인하면 묶음이 된다 (guest-feature-spec 6절).
 * S-13: 전략 3탭, 팀 카드(평균·편차·포지션), 설명, 두 선수 탭해서 교체, 확정.
 * S-14: 내 팀 강조, 배정 포지션, 상대 팀, 문장 설명. 수치 없음.
 */
import { Fragment, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { errorMessageWithDetails as errMsg } from '../api/client'
import { assignmentsApi } from '../api/assignments'
import { eventsApi } from '../api/events'
import { POSITIONS, type AttendanceView, type CandidateView, type ConstraintSet, type SquadView, type Strategy } from '../api/types'
import { Alert, Button, Card, GradeDot, SectionTitle, Spinner } from '../components/ui'
import { inSameLock, mergeLock } from '../lib/locks'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { FirstTimeTip } from '../components/tutorial'
import { AiExplainCard } from '../components/ai-cards'
import { SquadCard, rosterKey, type Marks } from '../components/adopted'
import { THREE_TEAM_FROM, THREE_TEAM_SUGGEST_FROM, squadName, squadStyle } from '../lib/squads'
import { josa } from '../lib/josa'
import { useDebounced } from '../lib/typewriter'

const STRATEGY_LABEL: Record<Strategy, string> = { SKILL: '실력 우선', CHEMISTRY: '친화도 우선', BALANCED: '종합' }
const teamName = squadName
/** 참석 N명을 T팀으로 가장 고르게: 21·3 → "7·7·7" */
const splitText = (n: number, t: number) => Array.from({ length: t }, (_, i) => Math.floor(n / t) + (i < n % t ? 1 : 0)).join('·')
/** "블랙으로" · "화이트로" · "레드로" — 받침에 맞춘다 */
const toTeam = (no: number) => `${teamName(no)}${josa(teamName(no), '으로')}`
/** from 팀 칸에서 to 팀 칸으로 — 칸이 오른쪽이면 "레드로 →", 왼쪽이면 "← 블랙으로" */
const moveLabel = (from: number, to: number, text: string) => (to > from ? `${text} →` : `← ${text}`)
const LOCK_COLORS = ['border-court-500 ring-brand-line', 'border-navy-500 ring-navy-200', 'border-emerald-500 ring-emerald-200', 'border-amber-500 ring-amber-200']

/* ============================ S-12 배정 실행 ============================ */
export function AssignPage() {
  const { eventId } = useParams()
  const id = Number(eventId)
  const nav = useNavigate()
  const ev = useQuery({ queryKey: ['events', id], queryFn: () => eventsApi.get(id) })
  const att = useQuery({ queryKey: ['events', id, 'attendances'], queryFn: () => eventsApi.attendances(id) })
  const sug = useQuery({ queryKey: ['events', id, 'suggestions'], queryFn: () => eventsApi.suggestions(id) })
  const [selected, setSelected] = useState<number[]>([])
  const [locks, setLocks] = useState<number[][]>([])
  const [seps, setSeps] = useState<number[][]>([])
  const [pins, setPins] = useState<Record<number, number>>({})
  const [threeChosen, setThreeChosen] = useState(false)
  const [dismissed, setDismissed] = useState<number[]>([])
  const [msg, setMsg] = useState<string | null>(null)

  const attendees: AttendanceView[] = useMemo(() => att.data?.items.filter((a) => a.status === 'ATTEND') ?? [], [att.data])
  const byId = useMemo(() => new Map(attendees.map((a) => [a.player.id, a.player])), [attendees])
  // 15명이 넘으면 3팀으로 나눌지 묻는다. 인원이 줄면 다시 2팀
  const canThree = attendees.length >= THREE_TEAM_FROM
  const teams: 2 | 3 = canThree && threeChosen ? 3 : 2
  const squadNos = teams === 3 ? [1, 2, 3] : [1, 2]
  const activePins = useMemo(() => Object.fromEntries(Object.entries(pins).filter(([, sq]) => sq <= teams)) as Record<number, number>, [pins, teams])
  const body = useMemo(() => ({
    team_count: teams,
    strategies: ['SKILL', 'CHEMISTRY', 'BALANCED'] as Strategy[],
    constraints: { lock_groups: locks, separate_groups: seps, pins: Object.entries(activePins).map(([pid, sq]) => ({ player_id: Number(pid), squad_no: sq })) } as ConstraintSet,
  }), [locks, seps, activePins, teams])

  // 조건을 바꿀 때마다 부르지 않고 0.3초 모아서. 조합마다 캐시에 쌓아 두지 않는다(gcTime 0)
  const settledBody = useDebounced(body, 300)
  const validate = useQuery({
    queryKey: ['events', id, 'validate', settledBody], queryFn: () => assignmentsApi.validate(id, settledBody),
    enabled: attendees.length > 0, gcTime: 0, placeholderData: (prev) => prev,
  })
  const run = useMutation({
    mutationFn: () => assignmentsApi.run(id, body),
    onSuccess: (r) => nav(`/assignments/runs/${r.id}`),
    onError: (e) => setMsg(errMsg(e, '팀을 나누지 못했어요.')),
  })
  const qc = useQueryClient()
  const closeRsvp = useMutation({
    mutationFn: () => eventsApi.closeRsvp(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['events'] }); setMsg('참석 응답을 마감했어요.') },
    onError: (e) => setMsg(errMsg(e, '마감하지 못했어요.')),
  })
  const loadLast = useMutation({
    mutationFn: () => assignmentsApi.lastConstraints(id),
    onSuccess: (c) => {
      const ids = new Set(byId.keys())
      setLocks(c.lock_groups.map((g) => g.filter((p) => ids.has(p))).filter((g) => g.length >= 2))
      setSeps(c.separate_groups.map((g) => g.filter((p) => ids.has(p))).filter((g) => g.length >= 2))
      setPins(Object.fromEntries(c.pins.filter((p) => ids.has(p.player_id)).map((p) => [p.player_id, p.squad_no])))
      setMsg('지난 일정의 조건을 불러왔어요. 이번에 불참인 사람은 뺐어요.')
    },
    onError: (e) => setMsg(errMsg(e, '지난 일정의 배정 기록이 없어요.')),
  })

  useEffect(() => { setSelected((s) => s.filter((pid) => byId.has(pid))) }, [byId])

  const lockIndexOf = (pid: number) => locks.findIndex((g) => g.includes(pid))
  const sepIndexOf = (pid: number) => seps.findIndex((g) => g.includes(pid))
  const toggle = (pid: number) => setSelected((s) => (s.includes(pid) ? s.filter((x) => x !== pid) : [...s, pid]))
  const addLock = (ids: number[]) => { setLocks((l) => mergeLock(l, ids)); setSelected([]) }  // 이미 묶인 사람이 있으면 그 묶음에 합친다
  const addSep = (ids: number[]) => { setSeps((l) => [...l, ids.slice(-2)]); setSelected([]) }  // 3명 이상이면 가장 오래 전에 고른 사람부터 뺀다
  const pinTo = (sq: number) => { setPins((p) => ({ ...p, ...Object.fromEntries(selected.map((pid) => [pid, sq])) })); setSelected([]) }
  const unpin = (pid: number) => setPins((p) => { const n = { ...p }; delete n[pid]; return n })
  const nextTeam = (sq: number) => (sq % teams) + 1
  const flipPin = (pid: number) => setPins((p) => ({ ...p, [pid]: nextTeam(p[pid]) }))

  if (ev.isLoading || att.isLoading) return <Screen><TopBar title="팀 배정" back={`/events/${id}`} /><Spinner /></Screen>
  if (!ev.data) return <Screen><TopBar title="팀 배정" back={`/events/${id}`} /><Content><Alert>일정을 불러오지 못했어요.</Alert></Content></Screen>
  const GRADE_ORDER: Record<string, number> = { A: 0, B: 1, C: 2, D: 3, E: 4 }
  const pool = attendees.filter((a) => !activePins[a.player.id]).sort((x, y) => {  // 등급순 — 게스트도 회원과 같이 섞어 정렬
    const gx = x.player.skill_grade ? GRADE_ORDER[x.player.skill_grade] : 9, gy = y.player.skill_grade ? GRADE_ORDER[y.player.skill_grade] : 9
    return gx - gy || x.player.display_name.localeCompare(y.player.display_name)
  })
  // 게스트와 초대한 사람이 이미 같은 묶음이면 승인할 게 없다. 다른 묶음에 있으면 제안은 남기고, 승인하면 두 묶음이 합쳐진다
  const suggestions = (sug.data?.items ?? []).filter((s) => !inSameLock(locks, s.guest.id, s.target.id))
  const approvable = suggestions.filter((s) => !dismissed.includes(s.guest.id))
  const approveAll = () => setLocks((l) => approvable.reduce((acc, s) => mergeLock(acc, [s.guest.id, s.target.id]), l))
  const feasible = settledBody === body && !validate.isPlaceholderData && (validate.data?.feasible ?? false)  // 이전 조건의 검사 결과로 켜지지 않게

  return (
    <Screen>
      <TopBar title="팀 배정" back={`/events/${id}`} right={<button className="mr-1 text-xs font-semibold text-brand-ink" onClick={() => loadLast.mutate()}>지난 조건 불러오기</button>} />
      <Content>
        <FirstTimeTip id="assign" />
        {msg && <Alert kind="info">{msg}</Alert>}
        {ev.data.rsvp_open && (
          <Card className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-ink">아직 참석 응답을 받고 있어요</p>
              <p className="text-xs text-muted">지금 마감하면 인원이 확정되고 팀원은 응답을 바꿀 수 없어요.</p>
            </div>
            <Button variant="secondary" className="min-h-10 shrink-0 whitespace-nowrap text-sm" loading={closeRsvp.isPending} onClick={() => confirm('참석 응답을 지금 마감할까요?') && closeRsvp.mutate()}>응답 마감</Button>
          </Card>
        )}
        {ev.data.adopted_candidate_id && <Alert kind="warn">이미 확정된 배정이 있어요. 새로 짠 배정안을 확정하기 전까지는 지금 배정이 그대로 보여요.</Alert>}

        {canThree && (
          <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-line bg-surface p-4">
            <input type="checkbox" checked={teams === 3} onChange={(e) => setThreeChosen(e.target.checked)} className="size-5 shrink-0 accent-brand" />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-ink">3팀으로 나누기</span>
              <span className="block text-xs text-muted">참석 {attendees.length}명을 {splitText(attendees.length, 3)}명씩 블랙 · 화이트 · 레드로 나눠요. 경기 기록은 쿼터마다 뛴 두 팀을 골라요.</span>
              {teams === 2 && attendees.length >= THREE_TEAM_SUGGEST_FROM && (
                <span className="mt-1.5 block text-xs font-semibold text-brand-ink">
                  2팀이면 한 팀이 {splitText(attendees.length, 2)}명이라 많이 쉬어요. 3팀으로 나눠 보는 건 어때요?
                </span>
              )}
            </span>
          </label>
        )}

        {suggestions.length > 0 && (
          <section>
            <SectionTitle action={approvable.length >= 2 && (
              <button className="text-xs font-semibold text-brand-ink" onClick={approveAll}>모두 승인 ({approvable.length})</button>
            )}>묶기 제안 {suggestions.length}</SectionTitle>
            <div className="space-y-2">
              {suggestions.map((s) => {
                const off = dismissed.includes(s.guest.id)
                const group = locks[lockIndexOf(s.target.id)]  // 초대한 사람이 이미 묶여 있으면 그 묶음에 추가된다
                return (
                  <Card key={s.guest.id} className={`flex items-center gap-3 py-3 ${off ? 'opacity-60' : ''}`}>
                    <p className="min-w-0 flex-1 text-sm leading-snug text-ink">
                      {group
                        ? <><b>{s.guest.display_name}</b>(게스트)을 <b>{s.target.display_name}</b>님 묶음({group.length}명)에 함께 넣을까요?</>
                        : <><b>{s.guest.display_name}</b>(게스트)을 <b>{s.target.display_name}</b>님과 같은 팀으로 묶을까요?</>}
                    </p>
                    {off ? (
                      <button className="text-xs font-semibold text-brand-ink" onClick={() => setDismissed((d) => d.filter((x) => x !== s.guest.id))}>무시 취소</button>
                    ) : (
                      <>
                        <Button className="min-h-9 text-xs" onClick={() => addLock([s.guest.id, s.target.id])}>승인</Button>
                        <button className="text-xs text-faint" onClick={() => setDismissed((d) => [...d, s.guest.id])}>무시</button>
                      </>
                    )}
                  </Card>
                )
              })}
            </div>
          </section>
        )}

        <section>
          <SectionTitle action={
            <span className="flex gap-3">
              {selected.length > 0 && <button className="text-xs text-muted" onClick={() => setSelected([])}>선택 해제</button>}
              {(locks.length > 0 || seps.length > 0 || Object.keys(pins).length > 0) && (
                <button className="text-xs font-semibold text-danger-ink" onClick={() => confirm('묶기·갈라놓기·미리 배치를 모두 지울까요?') && (setLocks([]), setSeps([]), setPins({}), setSelected([]))}>설정 초기화</button>
              )}
            </span>
          }>
            대기 칸 · 참석자 {attendees.length}명 {Object.keys(activePins).length > 0 && `(사전 배치 ${Object.keys(activePins).length}명 제외)`}
          </SectionTitle>
          <Card>
            <div className="flex flex-wrap gap-2">
              {pool.map((a) => {
                const p = a.player
                const on = selected.includes(p.id)
                const li = lockIndexOf(p.id)
                const si = sepIndexOf(p.id)
                return (
                  <button
                    key={p.id}
                    onClick={() => toggle(p.id)}
                    className={`relative flex min-h-10 items-center gap-1.5 rounded-full border-2 bg-surface pl-1 pr-3 text-sm font-semibold ${on ? 'border-court-500 bg-brand-soft ring-2 ring-brand-line' : li >= 0 ? LOCK_COLORS[li % LOCK_COLORS.length] + ' ring-2' : si >= 0 ? 'border-dashed border-danger-line' : 'border-line'}`}
                  >
                    <GradeDot grade={p.skill_grade} />
                    {p.display_name}
                    <span className="text-[10px] text-faint">{p.primary_position ?? '?'}</span>
                    {p.kind === 'GUEST' && <span className="text-[10px] text-faint">G</span>}
                    {a.team_lock_request_player_id && li < 0 && <span className="absolute -right-1 -top-1.5 rounded-full bg-court-500 px-1.5 text-[9px] text-white">제안</span>}
                  </button>
                )
              })}
              {pool.length === 0 && <p className="text-sm text-muted">참석 확정자가 없어요.</p>}
            </div>
            {selected.length >= 2 && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="secondary" className="min-h-10 text-sm" onClick={() => addLock(selected)}>같은 팀으로 묶기 ({selected.length})</Button>
                <Button variant="ghost" className="min-h-10 text-sm" onClick={() => addSep(selected)}>갈라놓기 (최대 2명)</Button>
              </div>
            )}
            {selected.length >= 1 && (
              <div className="mt-2 flex gap-2">
                {squadNos.map((sq) => (
                  <button key={sq} onClick={() => pinTo(sq)} className={`min-h-10 flex-1 rounded-xl border text-sm font-semibold ${squadStyle(sq).card}`}>{teamName(sq)}에 배치</button>
                ))}
              </div>
            )}
            {(locks.length > 0 || seps.length > 0) && (
              <div className="mt-3 space-y-1 text-xs text-muted">
                {locks.map((g, i) => <p key={`l${i}`}><span className={`mr-1 inline-block size-2 rounded-full ${['bg-court-500', 'bg-navy-500', 'bg-emerald-500', 'bg-amber-500'][i % 4]}`} />묶음: {g.map((p) => byId.get(p)?.display_name).join(' · ')} <button className="text-brand-ink" onClick={() => setLocks((l) => l.filter((_, j) => j !== i))}>해제</button></p>)}
                {seps.map((g, i) => <p key={`s${i}`}>갈라놓기: {g.map((p) => byId.get(p)?.display_name).join(' ↔ ')} <button className="text-brand-ink" onClick={() => setSeps((l) => l.filter((_, j) => j !== i))}>해제</button></p>)}
              </div>
            )}
          </Card>
        </section>

        <div className={`grid gap-2 ${teams === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {squadNos.map((sq) => {
            const list = attendees.filter((a) => activePins[a.player.id] === sq)
            const st = squadStyle(sq)
            const narrow = teams === 3
            return (
              <div key={sq} className={`min-h-24 rounded-2xl border-2 ${narrow ? 'p-2' : 'p-3'} ${st.card}`}>
                <p className={`${narrow ? 'text-xs' : 'text-sm'} font-bold`}>{teamName(sq)} {narrow ? '' : '사전 배치 '}({list.length}명)</p>
                {list.length === 0 ? <p className={`mt-3 text-center text-[11px] ${st.sub}`}>{narrow ? '고른 뒤 배치' : '이름을 고른 뒤 배치하세요'}</p> : (
                  <ul className={`mt-2 space-y-1 ${narrow ? 'text-xs' : 'text-sm'}`}>
                    {list.map((a) => (
                      <li key={a.player.id} className={narrow ? 'space-y-0.5' : 'flex items-center justify-between gap-2'}>
                        <span className="block truncate">{a.player.display_name}</span>
                        <span className="flex shrink-0 gap-2">
                          <button onClick={() => flipPin(a.player.id)} className="text-[11px] opacity-80">{moveLabel(sq, nextTeam(sq), toTeam(nextTeam(sq)))}</button>
                          <button onClick={() => unpin(a.player.id)} className="text-[11px] opacity-60">빼기</button>
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })}
        </div>

        {validate.data && (
          <div className="space-y-1">
            {validate.data.violations.map((v, i) => <Alert key={i}>{v.message}{v.player_ids.length ? ` — ${v.player_ids.map((p) => byId.get(p)?.display_name ?? p).join(', ')}` : ''}</Alert>)}
            {validate.data.warnings.map((w, i) => <Alert key={`w${i}`} kind="warn">{w}</Alert>)}
          </div>
        )}
      </Content>
      <BottomAction>
        <Button full loading={run.isPending} disabled={!feasible} onClick={() => run.mutate()}>{teams === 3 ? '3팀으로 ' : ''}3가지 배정안 만들기</Button>
      </BottomAction>
    </Screen>
  )
}

/* ============================ S-13 결과 (매니저) ============================ */
export function RunResultPage() {
  const { runId } = useParams()
  const id = Number(runId)
  const nav = useNavigate()
  const qc = useQueryClient()
  const run = useQuery({ queryKey: ['runs', id], queryFn: () => assignmentsApi.getRun(id) })
  const [tab, setTab] = useState(0)
  // 팀 번호 → 그 팀에서 고른 사람들 (많아야 두 팀). 묶음은 한 명을 탭해도 그룹 전체가 들어온다
  const [pick, setPick] = useState<Record<number, number[]>>({})
  const noPick: Record<number, number[]> = {}
  const [msg, setMsg] = useState<string | null>(null)
  // 옮기기 · 되돌리기는 이 실행만 바뀐다. 확정은 일정 화면(배정 결과)도 바뀐다
  const refresh = (events = false) => { qc.invalidateQueries({ queryKey: ['runs', id] }); if (events) qc.invalidateQueries({ queryKey: ['events'] }) }
  const exchange = useMutation({
    mutationFn: ({ cid, a, b, to }: { cid: number; a: number[]; b: number[]; to?: number }) => assignmentsApi.exchange(cid, a, b, to),
    onSuccess: () => { setPick(noPick); setMsg(null); refresh() },
    onError: (e) => setMsg(errMsg(e, '옮기지 못했어요.')),
  })
  const reset = useMutation({
    mutationFn: (cid: number) => assignmentsApi.reset(cid),
    onSuccess: () => { setPick(noPick); setMsg(null); refresh() },
    onError: (e) => setMsg(errMsg(e, '되돌리지 못했어요.')),
  })
  const adopt = useMutation({
    mutationFn: (cid: number) => assignmentsApi.adopt(cid),
    onSuccess: () => { refresh(true); nav(`/events/${run.data!.event_id}`, { replace: true }) },
    onError: (e) => setMsg(errMsg(e, '확정하지 못했어요.')),
  })

  if (run.isLoading) return <Screen><TopBar title="배정 결과" back="/" /><Spinner /></Screen>
  if (!run.data) return <Screen><TopBar title="배정 결과" back="/" /><Content><Alert>{errMsg(run.error, '결과를 불러오지 못했어요.')}</Alert></Content></Screen>
  const r = run.data
  const cand: CandidateView = r.candidates[Math.min(tab, r.candidates.length - 1)]
  const adoptedAny = r.candidates.some((c) => c.is_adopted)
  // 제약 표시용: 이 run 에 걸린 묶기 / 갈라놓기 / 사전 배치
  const marks = constraintMarks(r.constraints)
  const squadOf = (pid: number) => cand.squads.find((s) => s.members.some((m) => m.id === pid))?.squad_no
  const sepPartner = (pid: number) => marks.sepGroup.get(pid)?.find((x) => x !== pid)
  const lockMates = (pid: number) => marks.lockGroups.get(pid) ?? [pid]  // 묶음이면 그룹 전체, 아니면 본인만
  const toggleMany = (list: number[], ids: number[]) => (ids.every((x) => list.includes(x)) ? list.filter((x) => !ids.includes(x)) : [...list.filter((x) => !ids.includes(x)), ...ids])
  const onPick = (squadNo: number, pid: number) => {
    if (cand.is_adopted) return
    const partner = sepPartner(pid)
    const partnerSq = partner !== undefined ? squadOf(partner) : undefined
    if (partner !== undefined && partnerSq !== undefined && partnerSq !== squadNo) {
      // 갈라놓은 사람은 다른 팀의 짝과 함께 잡힌다 → 두 사람의 팀을 통째로 바꾸는 것만 가능
      const already = Object.values(pick).some((ids) => ids.includes(pid))
      setPick(already ? noPick : { [squadNo]: lockMates(pid), [partnerSq]: lockMates(partner) })
      return
    }
    setPick((p) => {
      const others = Object.entries(p).filter(([k, ids]) => Number(k) !== squadNo && ids.length)
      // 다른 팀에 갈라놓은 쌍이 잡혀 있거나, 이미 다른 두 팀에서 골랐으면 풀고 새로 고른다
      const reset = others.some(([, ids]) => ids.some((x) => sepPartner(x) !== undefined)) || (others.length >= 2)
      const base = reset ? noPick : p
      const next = { ...base, [squadNo]: toggleMany(base[squadNo] ?? [], lockMates(pid)) }
      return Object.fromEntries(Object.entries(next).filter(([, ids]) => ids.length)) as Record<number, number[]>
    })
  }
  const picked = Object.entries(pick).map(([k, ids]) => [Number(k), ids] as const).filter(([, ids]) => ids.length).sort((x, y) => x[0] - y[0])
  const pickedSep = picked.some(([, ids]) => ids.some((x) => sepPartner(x) !== undefined))
  const hasPick = picked.length > 0
  const three = cand.squads.length === 3
  const label = (ids: readonly number[]) => (ids.length === 1 ? '1명' : `${ids.length}명`)

  return (
    <Screen>
      <TopBar title="배정 결과" back={`/events/${r.event_id}/assign`} />
      <div className="grid grid-cols-3 border-b border-line bg-surface">
        {r.candidates.map((c, i) => (
          <button key={c.id} onClick={() => { setTab(i); setPick({}) }} className={`min-h-11 text-sm font-semibold ${tab === i ? 'border-b-2 border-court-500 text-brand-ink' : 'text-faint'}`}>
            {STRATEGY_LABEL[c.strategy]}{c.is_adopted ? ' ✓' : ''}
          </button>
        ))}
      </div>
      <Content>
        {r.warnings.map((w, i) => <Alert key={i} kind="warn">{w}</Alert>)}
        {msg && <Alert>{msg}</Alert>}
        <div className="rounded-xl bg-surface px-3 py-2 text-xs text-muted">
          <div className="flex items-center justify-between">
            <span>예상 실력 차이 <b className="text-ink">{cand.metrics.skill_spread}</b>점/쿼터</span>
            <span title="실력 차이, 포지션, 같이 뛰고 싶은 사람, 게스트가 한쪽에 몰리지 않는지를 합친 점수예요">균형 점수 {cand.total_score} <span className="text-faint">(낮을수록 좋음)</span></span>
          </div>
          <p className="mt-0.5 text-[11px] text-faint">{three ? '가장 강한 팀과 가장 약한 팀이 붙었을 때' : '두 팀이 붙었을 때'} 한 쿼터에 날 것으로 예상되는 점수 차예요. 0에 가까울수록 균형이 좋아요.</p>
        </div>
        {cand.metrics.manually_edited && (
          <div className="flex items-center justify-between rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn-ink">
            <span>이 안은 손으로 수정됐어요 (↔ 표시).</span>
            <button className="font-semibold text-brand-ink" disabled={reset.isPending} onClick={() => confirm('수동으로 옮긴 것을 모두 되돌릴까요?') && reset.mutate(cand.id)}>수동 수정 초기화</button>
          </div>
        )}
        <div className={`grid gap-2 ${three ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {cand.squads.map((s) => (
            <SquadCard key={s.squad_no} squad={s} picked={pick[s.squad_no] ?? []} onPick={(pid) => onPick(s.squad_no, pid)} showSkill marks={marks} narrow={three} />
          ))}
        </div>
        {!cand.is_adopted && hasPick && (
          <div className="space-y-2">
            {picked.length === 1 && cand.squads.filter((s) => s.squad_no !== picked[0][0]).map((s) => (
              <Button key={s.squad_no} variant="secondary" full loading={exchange.isPending} onClick={() => exchange.mutate({ cid: cand.id, a: [...picked[0][1]], b: [], to: s.squad_no })}>
                {moveLabel(picked[0][0], s.squad_no, `선택한 ${label(picked[0][1])}을 ${toTeam(s.squad_no)} 옮기기`)}
              </Button>
            ))}
            {picked.length === 2 && (
              <Button variant="secondary" full loading={exchange.isPending} onClick={() => exchange.mutate({ cid: cand.id, a: [...picked[0][1]], b: [...picked[1][1]] })}>
                {pickedSep ? '갈라놓은 두 사람의 팀을 서로 바꾸기 ↔' : `맞교체 ↔ (${teamName(picked[0][0])} ${label(picked[0][1])} ↔ ${teamName(picked[1][0])} ${label(picked[1][1])})`}
              </Button>
            )}
            {pickedSep && <p className="px-1 text-center text-xs text-muted">갈라놓기로 설정된 사람은 한 명만 옮길 수 없어요. 두 사람의 팀을 통째로 바꾸는 것만 가능해요.</p>}
            {!pickedSep && picked.some(([, ids]) => ids.some((x) => marks.locked.has(x))) && <p className="px-1 text-center text-xs text-muted">묶인 사람은 그룹이 함께 선택되고 함께 움직여요.</p>}
          </div>
        )}
        {!hasPick && !cand.is_adopted && (
          <p className="px-1 text-center text-xs text-faint">
            {three ? '사람을 탭한 뒤 옮길 팀을 고르거나, 두 팀에서 골라 맞교체할 수 있어요.' : '한 명을 탭하면 다른 팀으로 옮기고, 양 팀에서 골라 맞교체할 수 있어요.'} 팀에는 최소 5명이 남아야 해요.
            {(marks.locked.size > 0 || marks.pinned.size > 0 || marks.sepGroup.size > 0) && <><br />묶음은 함께 움직이고, 고정은 그대로, 분리는 짝과 팀을 바꿔요.</>}
          </p>
        )}
        <AiExplainCard candidateId={cand.id} rosterKey={rosterKey(cand.squads)} fallbackText={cand.explanation} />
        <PositionTable squads={cand.squads} />
      </Content>
      <BottomAction>
        {cand.is_adopted ? (
          <Button full variant="secondary" onClick={() => nav(`/events/${r.event_id}`)}>확정된 결과 보기</Button>
        ) : (
          <Button full loading={adopt.isPending} onClick={() => confirm(`[${STRATEGY_LABEL[cand.strategy]}] 배정안으로 확정할까요? 참석자에게 공개돼요.${adoptedAny ? ' (기존 확정은 해제)' : ''}`) && adopt.mutate(cand.id)}>
            이 배정안으로 확정
          </Button>
        )}
      </BottomAction>
    </Screen>
  )
}

/** run 의 제약을 표시용으로 정리한다: player_id → 묶음 번호·묶음 멤버 / 사전 배치 여부 / 갈라놓기 그룹 */
function constraintMarks(c: ConstraintSet): Marks {
  const locked = new Map<number, number>()
  const lockGroups = new Map<number, number[]>()
  c.lock_groups.forEach((g, i) => g.forEach((pid) => { locked.set(pid, i + 1); lockGroups.set(pid, g) }))
  const pinned = new Set(c.pins.map((p) => p.player_id))
  const sepGroup = new Map<number, number[]>()
  c.separate_groups.forEach((g) => g.forEach((pid) => sepGroup.set(pid, g)))
  return { locked, lockGroups, pinned, sepGroup }
}

function PositionTable({ squads }: { squads: SquadView[] }) {
  return (
    <Card>
      <p className="mb-2 text-sm font-bold text-ink">포지션 슬롯</p>
      <div className="grid grid-cols-6 gap-1 text-center text-xs">
        <span />
        {POSITIONS.map((p) => <span key={p} className="font-semibold text-muted">{p}</span>)}
        {squads.map((s) => (
          <Fragment key={s.squad_no}>
            <span className="text-left font-semibold text-ink">{s.squad_name}</span>
            {POSITIONS.map((p) => {
              const n = Object.values(s.assigned_positions).filter((x) => x === p).length
              return <span key={`${s.squad_no}${p}`} className={`rounded py-0.5 ${n ? 'bg-info-soft text-ink' : 'bg-danger-soft text-danger-ink'}`}>{n}</span>
            })}
          </Fragment>
        ))}
      </div>
    </Card>
  )
}

/* ============================ S-14 확정 결과 (전원) ============================ */
/** 예전 배정 결과 주소(/events/:id/assignment) — 이제 일정 화면이 곧 배정 결과라 그리로 보낸다 */
export function AdoptedPage() {
  const { eventId } = useParams()
  return <Navigate to={`/events/${eventId}`} replace />
}
