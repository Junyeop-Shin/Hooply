/**
 * 전술 편집기 (docs/07 FR-57 ~ FR-59, S-30). 경로: /teams/:teamId/plays/new · /teams/:teamId/plays/:playId/edit
 * 팀원 누구나 만든다. 고치기 · 지우기는 만든 사람과 매니저 (v1.7).
 *
 * 1. 시작 위치 — 동그라미를 끌어서 옮기고, 처음 공을 가질 사람을 고른다
 * 2. 단계 — 단계를 고른 뒤 "누가(동그라미) → 무엇을(칩) → 누구에게(동그라미) / 어디로(코트)" 순서로 누르면 동작이 들어간다.
 *    한 단계 안의 동작은 동시에 재생된다. 같은 사람이 한 단계에 두 동작을 하면 새 것으로 바뀐다
 * 3. 그리는 동안 서버가 재생 가능성을 검사하고(어느 단계가 왜 안 되는지) 동작에서 역할을 뽑는다(규칙)
 * 4. "AI로 역할 붙이기"(체인 D) — 전술의 의도까지 읽어 역할을 고친다. 매니저가 자리마다 직접 바꿀 수도 있다
 * 5. 이 전술이 가정한 상대 수비(맨투맨 · 지역 2-3)와 스크린 대응(스위치 · 스테이) — 전술판의 수비가 이대로 움직인다.
 *    기본 전술은 이 값이 고정이고, 여기서만 고른다 (v1.7)
 * 6. 미리 보기(상대 수비 포함) · 막히면 · 저장
 */
import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { teamPlaysApi } from '../api/tactics'
import type { CourtPoint, OppDefense, Play, PlayAction, PlayActionType, PlayStep, RoleSource, ScreenCall, Situation, TacticRole, TeamPlayIn } from '../api/types'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { ActionMark, Court, H, OOB_H, R, TONE, TacticBoard, W, sx, sy } from '../components/tactic-board'
import { CIRCLED } from '../components/tactics'
import { Alert, Button, Field, SectionTitle, Spinner } from '../components/ui'
import { ROLE_LABEL, renderCounter, stepStates } from '../lib/tactics'
import { useDebounced } from '../lib/typewriter'

const ACTION_LABEL: Record<PlayActionType, string> = {
  move: '이동', dribble: '드리블', pass: '패스', screen: '스크린', cut: '컷', handoff: '핸드오프', shot: '슛',
}
const BALL_TYPES: PlayActionType[] = ['dribble', 'pass', 'handoff', 'shot']
const OFF_TYPES: PlayActionType[] = ['move', 'cut', 'screen']
const ROLES = Object.keys(ROLE_LABEL) as TacticRole[]
const DEFAULT_START: CourtPoint[] = [
  { x: 0.5, y: 0.66 }, { x: 0.85, y: 0.48 }, { x: 0.15, y: 0.48 }, { x: 0.34, y: 0.16 }, { x: 0.66, y: 0.16 },
]

/** 동작 설명 자동 문장: "5번 스크린 → 1번 · 1번 드리블" */
const autoCaption = (actions: PlayAction[]) =>
  actions.map((a) => `${a.slot}번 ${ACTION_LABEL[a.type]}${a.target ? ` → ${a.target}번` : ''}`).join(' · ').slice(0, 80)

interface Pending { slot: number; type?: PlayActionType; target?: number }

export function PlayEditorPage() {
  const { teamId: tid = '', playId: pidParam } = useParams()
  const teamId = Number(tid)
  const playId = pidParam ? Number(pidParam) : null
  const existing = useQuery({ queryKey: ['tactics', 'team-play', teamId, playId], queryFn: () => teamPlaysApi.get(teamId, playId!), enabled: playId !== null, retry: false })
  if (existing.data && !existing.data.can_edit) {
    return (
      <Screen>
        <TopBar title="전술 고치기" back={`/tactics/team_${playId}?team=${teamId}`} />
        <Content><Alert>만든 사람이나 매니저만 고칠 수 있어요.</Alert></Content>
      </Screen>
    )
  }
  if (playId !== null && !existing.data) {
    return (
      <Screen>
        <TopBar title="전술 고치기" back={`/teams/${teamId}`} />
        {existing.isLoading ? <Spinner /> : <Content><Alert>{existing.error instanceof ApiError ? existing.error.message : '전술을 불러오지 못했어요.'}</Alert></Content>}
      </Screen>
    )
  }
  return <Editor key={playId ?? 'new'} teamId={teamId} playId={playId} initial={existing.data?.play ?? null} initialSource={existing.data?.role_source ?? 'RULE'} />
}

function Editor({ teamId, playId, initial, initialSource }: { teamId: number; playId: number | null; initial: Play | null; initialSource: RoleSource }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [name, setName] = useState(initial?.name ?? '')
  const [summary, setSummary] = useState(initial?.summary === '우리 팀이 만든 전술' ? '' : initial?.summary ?? '')
  const [oppDefense, setOppDefense] = useState<OppDefense>(initial?.opp_defense ?? (initial?.defense === 'zone' ? 'zone' : 'man'))
  const [screenCall, setScreenCall] = useState<ScreenCall>(initial?.screen_call ?? 'stay')
  const [situation, setSituation] = useState<Situation>(initial?.situation ?? 'half_court')
  const [counter, setCounter] = useState(initial?.counter ?? '')
  const [start, setStart] = useState<CourtPoint[]>(initial?.start ?? DEFAULT_START)
  const [ball, setBall] = useState(initial?.ball ?? 1)
  const [steps, setSteps] = useState<PlayStep[]>(initial?.steps ?? [])
  const [edited, setEdited] = useState<Set<number>>(() => new Set(initial ? initial.steps.map((_, i) => i) : [])) // 직접 고친 단계 설명
  const [mode, setMode] = useState<'start' | number>('start')
  const [pending, setPending] = useState<Pending | null>(null)
  const [roles, setRoles] = useState<TacticRole[] | null>(initial?.roles ?? null) // null = 규칙 추출을 따라간다
  const [roleSource, setRoleSource] = useState<RoleSource>(initialSource)
  const [reasons, setReasons] = useState<string[] | null>(null)
  const [rolesFor, setRolesFor] = useState<string | null>(null) // 역할을 붙일 때의 동작 (바뀌면 다시 붙이라고 알린다)

  // 서버에 보낼 값 — 빈 단계는 빼고, 비어 있는 설명은 자동 문장으로
  const body: TeamPlayIn = useMemo(() => ({
    name, summary, defense: null, opp_defense: oppDefense, screen_call: screenCall, situation, counter, start, ball,
    steps: steps.filter((s) => s.actions.length).map((s) => ({ caption: s.caption.trim() || autoCaption(s.actions), actions: s.actions })),
    roles, role_source: roles ? roleSource : 'RULE',
  }), [name, summary, oppDefense, screenCall, situation, counter, start, ball, steps, roles, roleSource])
  const shape = JSON.stringify({ start: body.start, ball: body.ball, steps: body.steps.map((s) => s.actions), situation })
  const settled = useDebounced(shape, 400)
  const check = useQuery({
    queryKey: ['tactics', 'play-check', teamId, settled],
    queryFn: () => teamPlaysApi.check(teamId, { ...body, roles: null }),
    enabled: body.steps.length > 0 && settled === shape,
    placeholderData: (prev) => prev, retry: false,
  })
  const shownRoles: TacticRole[] = roles ?? check.data?.roles ?? (['spacer', 'spacer', 'spacer', 'spacer', 'spacer'] as TacticRole[])
  const shownReasons = reasons ?? (roles ? null : check.data?.reasons) ?? null
  const playable = body.steps.length > 0 && !!check.data?.playable && settled === shape

  // 편집 중 상태: 고른 단계를 시작할 때의 위치와 공
  const draftPlay: Play = {
    key: 'draft', name: name || '새 전술', summary, defense: oppDefense, opp_defense: oppDefense, screen_call: screenCall,
    situation, counter, start, ball, roles: shownRoles, steps,
  }
  const states = stepStates(draftPlay)
  const k = mode === 'start' ? null : mode
  const before = k === null ? states[0] : states[k]
  const holder = before.holder

  const ai = useMutation({
    mutationFn: () => teamPlaysApi.aiRoles(teamId, { ...body, roles: null }),
    onSuccess: (r) => { setRoles(r.roles); setReasons(r.reasons); setRoleSource(r.source === 'AI' ? 'AI' : 'RULE'); setRolesFor(shape) },
  })
  const save = useMutation({
    mutationFn: () => (playId ? teamPlaysApi.update(teamId, playId, body) : teamPlaysApi.create(teamId, body)),
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ['tactics', 'team-plays', teamId] })
      qc.setQueryData(['tactics', 'team-play', teamId, v.id], v)
      nav(`/tactics/team_${v.id}?team=${teamId}`, { replace: true })
    },
  })
  const remove = useMutation({
    mutationFn: () => teamPlaysApi.remove(teamId, playId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tactics', 'team-plays', teamId] }); nav(`/teams/${teamId}`, { replace: true }) },
  })

  const setStep = (i: number, next: PlayStep) => setSteps((ss) => ss.map((s, j) => (j === i ? next : s)))
  const addAction = (a: PlayAction) => {
    if (k === null) return
    const cur = steps[k]
    const isBall = BALL_TYPES.includes(a.type)
    // 한 사람은 한 단계에 동작 하나, 공 동작도 한 단계에 하나 — 겹치면 새 것으로 바꾼다
    const kept = cur.actions.filter((x) => x.slot !== a.slot && !(isBall && BALL_TYPES.includes(x.type)))
    const actions = [...kept, a].sort((x, y) => x.slot - y.slot)
    setStep(k, { caption: edited.has(k) ? cur.caption : autoCaption(actions), actions })
    setPending(null)
  }
  const removeAction = (i: number) => {
    if (k === null) return
    const actions = steps[k].actions.filter((_, j) => j !== i)
    setStep(k, { caption: edited.has(k) ? steps[k].caption : autoCaption(actions), actions })
  }
  const addStep = () => {
    setSteps((ss) => [...ss, { caption: '', actions: [] }])
    setMode(steps.length)
    setPending(null)
  }
  const deleteStep = () => {
    if (k === null) return
    setSteps((ss) => ss.filter((_, j) => j !== k))
    setEdited((e) => new Set([...e].filter((j) => j !== k).map((j) => (j > k ? j - 1 : j))))
    setMode(k > 0 ? k - 1 : 'start')
    setPending(null)
  }

  const tapSlot = (slot: number) => {
    if (k === null) return
    if (pending?.type && ['pass', 'handoff', 'screen'].includes(pending.type) && pending.target === undefined) {
      if (slot === pending.slot) return
      if (pending.type === 'screen') { setPending({ ...pending, target: slot }); return }
      addAction({ type: pending.type, slot: pending.slot, to: null, target: slot })
      return
    }
    setPending({ slot })
  }
  const tapCourt = (p: CourtPoint) => {
    if (k === null || !pending?.type) return
    if (['move', 'cut', 'dribble'].includes(pending.type)) addAction({ type: pending.type, slot: pending.slot, to: p, target: null })
    else if (pending.type === 'screen' && pending.target !== undefined) addAction({ type: 'screen', slot: pending.slot, to: p, target: pending.target })
  }
  const chooseType = (t: PlayActionType) => {
    if (!pending) return
    if (t === 'shot') { addAction({ type: 'shot', slot: pending.slot, to: null, target: null }); return }
    setPending({ slot: pending.slot, type: t })
  }

  const prompt = k === null
    ? '동그라미를 끌어 시작 위치를 정해요.'
    : !pending ? '움직일 사람(동그라미)을 누르세요.'
      : !pending.type ? `${pending.slot}번이 무엇을 할까요?`
        : pending.type === 'pass' || pending.type === 'handoff' ? `${pending.slot}번이 누구에게 ${ACTION_LABEL[pending.type]}할까요? 받을 사람을 누르세요.`
          : pending.type === 'screen' && pending.target === undefined ? `${pending.slot}번이 누구에게 스크린을 걸까요? 동료를 누르세요.`
            : pending.type === 'screen' ? '스크린을 설 자리를 코트에서 누르세요.'
              : `${pending.slot}번이 어디로 ${ACTION_LABEL[pending.type]}할까요? 코트를 누르세요.`
  const saveError = save.error instanceof ApiError ? save.error : null

  return (
    <Screen>
      <TopBar title={playId ? '전술 고치기' : '새 전술 만들기'} back={playId ? `/tactics/team_${playId}?team=${teamId}` : `/teams/${teamId}`} />
      <Content>
        <section className="space-y-3">
          <Field label="전술 이름" value={name} maxLength={30} onChange={(e) => setName(e.target.value)} placeholder="예: 우리 팀 픽앤롤" />
          <Field label="한 줄 설명 (선택)" value={summary} maxLength={80} onChange={(e) => setSummary(e.target.value)} placeholder="예: 빅맨 스크린 뒤 골밑으로" />
          <Choice label="상대 수비" value={oppDefense} onChange={setOppDefense} options={[['man', '맨투맨'], ['zone', '지역 (2-3)']]} />
          <Choice label="스크린 대응" value={screenCall} onChange={setScreenCall} options={[['switch', '스위치'], ['stay', '스테이']]} />
          <p className="-mt-1 px-1 text-[11px] text-muted">
            이 전술이 가정한 상대 수비예요. 전술판의 수비가 이대로 움직이고, 추천도 이 수비 상대로만 해요.
            {screenCall === 'switch' ? ' 스위치: 스크린을 만나면 두 수비가 막을 사람을 바꿔요.' : ' 스테이: 스크린에 걸린 수비가 돌아서 끝까지 따라와요.'}
          </p>
          <Choice label="상황" value={situation} onChange={setSituation} options={[['half_court', '하프코트'], ['inbound', '인바운드']]} />
        </section>

        <section className="space-y-2">
          <SectionTitle>움직임 그리기</SectionTitle>
          <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="tablist" aria-label="단계">
            <StepTab active={mode === 'start'} onClick={() => { setMode('start'); setPending(null) }}>시작 위치</StepTab>
            {steps.map((s, i) => (
              <StepTab key={i} active={mode === i} onClick={() => { setMode(i); setPending(null) }} warn={!s.actions.length}>{i + 1}단계</StepTab>
            ))}
            <StepTab active={false} onClick={addStep}>+ 단계</StepTab>
          </div>
          <p className="min-h-5 px-1 text-sm font-semibold text-ink" aria-live="polite">{prompt}</p>
          <EditorCourt
            positions={before.pos} holder={holder} inbound={situation === 'inbound'}
            actions={k !== null ? steps[k].actions : []} to={k !== null ? states[k + 1].pos : before.pos}
            selected={pending?.slot ?? null} targeting={pending?.target ?? null}
            onDrag={k === null ? (slot, p) => setStart((ps) => ps.map((q, i) => (i === slot - 1 ? p : q))) : undefined}
            onTapSlot={tapSlot} onTapCourt={tapCourt}
          />
          {k === null ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted">처음 공</span>
              {[1, 2, 3, 4, 5].map((s) => (
                <button key={s} type="button" aria-pressed={ball === s} onClick={() => setBall(s)} className={`min-h-10 min-w-10 rounded-full text-sm font-bold ${ball === s ? 'bg-brand text-on-brand' : 'border border-line bg-surface text-ink-2'}`}>{s}</button>
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {pending && !pending.type && (
                <div className="flex flex-wrap gap-1.5" aria-label="동작 고르기">
                  {(pending.slot === holder ? BALL_TYPES : OFF_TYPES).map((t) => (
                    <button key={t} type="button" onClick={() => chooseType(t)} className="min-h-10 rounded-full border border-brand-line bg-brand-soft px-3.5 text-sm font-bold text-brand-ink">{ACTION_LABEL[t]}</button>
                  ))}
                  <button type="button" onClick={() => setPending(null)} className="min-h-10 px-2 text-sm text-muted">취소</button>
                </div>
              )}
              {holder === null && <Alert kind="warn">앞 단계에서 슛을 해서 공이 없어요. 이 단계는 지우거나 앞 단계를 고쳐 주세요.</Alert>}
              <ul className="space-y-1">
                {steps[k].actions.map((a, i) => (
                  <li key={i} className="flex min-h-10 items-center gap-2 rounded-xl bg-sunken px-3 text-sm">
                    <span className="flex-1 text-ink">{a.slot}번 {ACTION_LABEL[a.type]}{a.target ? ` → ${a.target}번` : ''}</span>
                    <button type="button" onClick={() => removeAction(i)} aria-label={`${a.slot}번 ${ACTION_LABEL[a.type]} 지우기`} className="size-9 text-lg text-faint">×</button>
                  </li>
                ))}
              </ul>
              <Field
                label={`${k + 1}단계 설명`} value={steps[k].caption} maxLength={80}
                onChange={(e) => { setEdited((s) => new Set(s).add(k)); setStep(k, { ...steps[k], caption: e.target.value }) }}
                placeholder="비워 두면 동작으로 자동으로 적어요"
              />
              <Button variant="danger" onClick={deleteStep}>{k + 1}단계 지우기</Button>
            </div>
          )}
          {check.data && !check.data.playable && body.steps.length > 0 && (
            <Alert kind="warn">
              <span className="block font-semibold">이대로는 재생할 수 없어요</span>
              {check.data.errors.map((e) => <span key={e} className="block">{e}</span>)}
            </Alert>
          )}
        </section>

        {playable && (
          <section className="space-y-2">
            <SectionTitle>미리 보기</SectionTitle>
            <TacticBoard key={`${shape}${oppDefense}${screenCall}`} play={{ ...draftPlay, steps: body.steps }} />
          </section>
        )}

        <section className="space-y-2">
          <SectionTitle action={
            <button type="button" onClick={() => ai.mutate()} disabled={!playable || ai.isPending} className="text-sm font-semibold text-brand-ink disabled:opacity-40">
              {ai.isPending ? 'AI가 읽는 중…' : 'AI로 역할 붙이기'}
            </button>
          }>
            자리별 역할
          </SectionTitle>
          <p className="px-1 text-xs text-muted">
            {roles === null ? '움직임에서 자동으로 뽑은 역할이에요. 추천할 때 이 역할에 맞는 사람을 앉혀요.'
              : roleSource === 'AI' ? 'AI가 전술의 의도까지 읽고 붙인 역할이에요.' : roleSource === 'MANAGER' ? '직접 정한 역할이에요.' : 'AI를 쓸 수 없어 움직임으로 붙인 역할이에요.'}
            {roles && rolesFor && rolesFor !== shape && ' 움직임을 바꿨다면 다시 붙여 보세요.'}
          </p>
          {ai.isError && <Alert>{ai.error instanceof ApiError ? ai.error.message : '역할을 붙이지 못했어요.'}</Alert>}
          <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
            {shownRoles.map((r, i) => (
              <li key={i} className="flex items-start gap-3 px-4 py-2.5">
                <span className="w-5 pt-2 text-center text-sm font-bold text-brand-ink">{CIRCLED[i]}</span>
                <div className="min-w-0 flex-1">
                  <label className="sr-only" htmlFor={`role-${i}`}>{i + 1}번 역할</label>
                  <select
                    id={`role-${i}`} value={r}
                    onChange={(e) => { const next = [...shownRoles]; next[i] = e.target.value as TacticRole; setRoles(next); setRoleSource('MANAGER'); setReasons(null); setRolesFor(shape) }}
                    className="min-h-10 w-full rounded-xl border border-line bg-surface px-2 text-sm text-ink"
                  >
                    {ROLES.map((x) => <option key={x} value={x}>{ROLE_LABEL[x]}</option>)}
                  </select>
                  {shownReasons?.[i] && <p className="mt-1 text-xs text-muted">{shownReasons[i]}</p>}
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="space-y-2">
          <SectionTitle>막히면 (선택)</SectionTitle>
          <CounterInput value={counter} onChange={setCounter} />
          {counter.trim() && <p className="px-1 text-xs text-muted">보이는 모습: {renderCounter(counter)}</p>}
        </section>

        {saveError && (
          <Alert>
            <span className="block font-semibold">{saveError.message}</span>
            {saveError.details.map((d, i) => <span key={i} className="block">{d.reason}</span>)}
          </Alert>
        )}
        {playId && (
          <Button variant="danger" full loading={remove.isPending} onClick={() => { if (window.confirm('이 전술을 지울까요? 자리 배치와 댓글도 함께 지워져요.')) remove.mutate() }}>
            전술 지우기
          </Button>
        )}
      </Content>
      <BottomAction>
        <Button full loading={save.isPending} disabled={!name.trim() || !playable} onClick={() => save.mutate()}>
          {!name.trim() ? '이름을 적어 주세요' : !playable ? '움직임을 완성해 주세요' : playId ? '고친 내용 저장' : '전술 저장'}
        </Button>
      </BottomAction>
    </Screen>
  )
}

function StepTab({ active, warn, onClick, children }: { active: boolean; warn?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button" role="tab" aria-selected={active} onClick={onClick}
      className={`min-h-10 shrink-0 rounded-full px-3.5 text-sm font-bold ${active ? 'bg-bar text-bar-ink' : warn ? 'border border-warn-line bg-warn-soft text-warn-ink' : 'border border-line bg-surface text-ink-2'}`}
    >
      {children}
    </button>
  )
}

function Choice<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium text-ink">{label}</p>
      <div role="radiogroup" aria-label={label} className="grid rounded-xl bg-sunken p-1" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>
        {options.map(([v, text]) => (
          <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)} className={`min-h-10 rounded-lg text-sm font-bold ${value === v ? 'bg-surface text-ink shadow' : 'text-muted'}`}>{text}</button>
        ))}
      </div>
    </div>
  )
}

/** 막히면 문장 — ①~⑤ 칩을 누르면 {n} 이 들어가고, 그날 배치가 있으면 선수 이름으로 바뀐다 */
function CounterInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const insert = (n: number) => {
    const el = ref.current
    const at = el ? el.selectionStart : value.length
    const next = `${value.slice(0, at)}{${n}}${value.slice(at)}`.slice(0, 120)
    onChange(next)
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + 3, at + 3) })
  }
  return (
    <div className="space-y-1.5">
      <label className="sr-only" htmlFor="counter">막히면</label>
      <textarea
        id="counter" ref={ref} rows={2} value={value} maxLength={120} onChange={(e) => onChange(e.target.value)}
        placeholder="예: {5}의 롤이 막히면 코너 {2}에게 빼 줘요"
        className="block w-full resize-none rounded-xl border border-line bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
      />
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-muted">자리 넣기</span>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" onClick={() => insert(n)} aria-label={`${n}번 자리 넣기`} className="min-h-9 min-w-9 rounded-full border border-line bg-surface text-sm font-bold text-brand-ink">{CIRCLED[n - 1]}</button>
        ))}
      </div>
    </div>
  )
}

/** 편집용 코트 — 시작 위치에서는 끌어서 옮기고, 단계에서는 동그라미·코트를 눌러 동작을 넣는다 */
function EditorCourt({ positions, to, holder, inbound, actions, selected, targeting, onDrag, onTapSlot, onTapCourt }: {
  positions: CourtPoint[]; to: CourtPoint[]; holder: number | null; inbound: boolean; actions: PlayAction[]
  selected: number | null; targeting: number | null
  onDrag?: (slot: number, p: CourtPoint) => void; onTapSlot: (slot: number) => void; onTapCourt: (p: CourtPoint) => void
}) {
  const svg = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<number | null>(null)
  const top = inbound ? OOB_H : 0
  const colors = TONE.neutral

  const toCourt = (e: { clientX: number; clientY: number }): CourtPoint | null => {
    const el = svg.current
    const ctm = el?.getScreenCTM()
    if (!el || !ctm) return null
    const pt = el.createSVGPoint()
    pt.x = e.clientX; pt.y = e.clientY
    const p = pt.matrixTransform(ctm.inverse())
    const r3 = (v: number) => Math.round(v * 1000) / 1000
    return { x: r3(Math.min(0.97, Math.max(0.03, p.x / W))), y: r3(Math.min(0.97, Math.max(inbound ? -0.07 : 0.02, p.y / H))) }
  }
  const move = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (drag === null || !onDrag) return
    const p = toCourt(e)
    if (p) onDrag(drag, p)
  }
  return (
    <svg
      ref={svg} viewBox={`0 ${-top} ${W} ${H + top}`} className="w-full touch-none select-none rounded-2xl" role="group" aria-label="전술 편집 코트"
      onPointerMove={move} onPointerUp={() => setDrag(null)} onPointerLeave={() => setDrag(null)}
    >
      <defs>
        <marker id="ed-ah" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
          <path d="M0,0 L6,3 L0,6 z" style={{ fill: 'var(--color-ink)' }} />
        </marker>
      </defs>
      {inbound && <rect x={0} y={-top} width={W} height={top} style={{ fill: 'var(--color-sunken)' }} />}
      <g onClick={(e) => { const p = toCourt(e); if (p) onTapCourt(p) }}>
        {inbound && <rect x={0} y={-top} width={W} height={top} fill="transparent" />}
        <Court />
      </g>
      <g pointerEvents="none">
        {actions.map((a, i) => <ActionMark key={i} a={a} from={positions} to={to} arrow="url(#ed-ah)" brandArrow="url(#ed-ah)" />)}
        {actions.filter((a) => a.to).map((a, i) => (
          <circle key={`g${i}`} cx={sx(a.to!)} cy={sy(a.to!)} r={R} style={{ fill: 'none', stroke: 'var(--color-ink)' }} strokeWidth={0.5} strokeDasharray="1.4 1.2" />
        ))}
      </g>
      {positions.map((p, i) => {
        const slot = i + 1
        const ring = selected === slot ? 'var(--color-court-500)' : targeting === slot ? 'var(--color-info-ink)' : null
        return (
          <g
            key={i} role="button" aria-label={`${slot}번`} className="cursor-pointer"
            onPointerDown={(e) => { if (onDrag) { e.preventDefault(); svg.current?.setPointerCapture(e.pointerId); setDrag(slot) } }}
            onClick={(e) => { e.stopPropagation(); if (!onDrag) onTapSlot(slot) }}
          >
            <circle cx={sx(p)} cy={sy(p)} r={R + 4} fill="transparent" />
            {ring && <circle cx={sx(p)} cy={sy(p)} r={R + 1.8} style={{ fill: 'none', stroke: ring }} strokeWidth={1.2} />}
            <circle cx={sx(p)} cy={sy(p)} r={R} style={{ fill: colors.fill, stroke: colors.stroke }} strokeWidth={0.6} />
            <text x={sx(p)} y={sy(p) + 1.9} textAnchor="middle" fontSize={5.4} fontWeight={800} style={{ fill: colors.ink }}>{slot}</text>
            {holder === slot && <circle cx={sx(p) + 4} cy={sy(p) + 3.4} r={2.3} style={{ fill: 'var(--color-court-500)' }} stroke="#7c2d12" strokeWidth={0.5} />}
          </g>
        )
      })}
    </svg>
  )
}
