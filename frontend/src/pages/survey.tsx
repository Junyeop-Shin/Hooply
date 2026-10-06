/**
 * S-03 온보딩 설문 (survey-feature-spec 8절, v2 문항).
 * 문항 카드 1개씩 · 진행률 바 · 이전/다음 · 응답 전엔 다음 비활성 · 마지막은 [제출하기].
 * 단일선택 문항은 고르는 즉시 다음으로 넘어간다. group_label 이 같은 문항(D3A/D3B)은 한 화면에 묶는다.
 * D 섹션 다중선택(가능 포지션)은 고른 순서가 선호 순서이므로 칩에 순번을 표시한다.
 * 이미 제출했으면 홈으로 리다이렉트.
 *
 * SelfRankPage — "이 동호회에서 내 실력 위치" (구 E3). 팀 가입 직후 팀별로 한 번 묻는다.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { STATIC_QUERY } from '../queryClient'
import { surveyApi } from '../api/survey'
import { errorMessage, errorMessageWithDetails } from '../api/client'
import { SELF_RANK_LABEL, type SelfRankLevel, type SurveyAnswerIn, type SurveyQuestion } from '../api/types'
import { useMe } from './home'
import { Alert, Button, LoadError, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar, useGoBack } from '../components/layout'

type Answer = { optionIds: number[]; numeric?: number }

const SECTION_NAME: Record<string, string> = { A: '기본', B: '공격', C: '수비', D: '포지션', E: '성향' }
const AUTO_ADVANCE_MS = 260

/** 답하던 설문을 이 탭에 보관 — 새로고침하거나 잠깐 다른 화면에 다녀와도 이어서 한다. 제출하면 지운다 */
const surveyDraftKey = (templateId: number) => `survey-draft-${templateId}`
type SurveyDraft = { step: number; answers: Record<number, Answer> }
function readSurveyDraft(templateId: number, steps: number): SurveyDraft | null {
  try {
    const raw = sessionStorage.getItem(surveyDraftKey(templateId))
    if (!raw) return null
    const d = JSON.parse(raw) as SurveyDraft
    if (typeof d.step !== 'number' || typeof d.answers !== 'object' || d.answers === null) return null
    return { step: Math.min(Math.max(0, d.step), steps - 1), answers: d.answers }
  } catch { return null }
}

export function SurveyPage() {
  const me = useMe()
  const tpl = useQuery({ queryKey: ['survey', 'template'], queryFn: surveyApi.template, ...STATIC_QUERY })
  if (me.data?.onboarding_completed) return <Navigate to="/" replace />
  if (me.isLoading || tpl.isLoading) return <Screen><TopBar title="실력 설문" /><Spinner page /></Screen>
  if (!tpl.data) return <Screen><TopBar title="실력 설문" back="/" /><Content><LoadError message={errorMessage(tpl.error, '설문을 불러오지 못했어요.')} onRetry={() => tpl.refetch()} retrying={tpl.isFetching} /></Content></Screen>
  return <SurveyForm questions={tpl.data.questions} templateId={tpl.data.template_id} />
}

/** group_label 이 같은 연속 문항을 한 "화면(step)"으로 묶는다 */
function groupSteps(questions: SurveyQuestion[]): SurveyQuestion[][] {
  const steps: SurveyQuestion[][] = []
  for (const q of questions) {
    const last = steps[steps.length - 1]
    if (q.group_label && last && last[0].group_label === q.group_label) last.push(q)
    else steps.push([q])
  }
  return steps
}

const isSingle = (q: SurveyQuestion) => q.answer_type !== 'MULTI_CHIP' && q.answer_type !== 'STEPPER'

function SurveyForm({ questions, templateId }: { questions: SurveyQuestion[]; templateId: number }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const steps = useMemo(() => groupSteps(questions), [questions])
  const [initial] = useState(() => readSurveyDraft(templateId, steps.length))
  const [step, setStep] = useState(initial?.step ?? 0)
  const [answers, setAnswers] = useState<Record<number, Answer>>(initial?.answers ?? {})
  useEffect(() => {
    try { sessionStorage.setItem(surveyDraftKey(templateId), JSON.stringify({ step, answers })) } catch { /* 저장소 없음 */ }
  }, [templateId, step, answers])
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const current = steps[step]
  const done = (q: SurveyQuestion, a?: Answer) => (q.answer_type === 'STEPPER' ? a?.numeric !== undefined : (a?.optionIds.length ?? 0) > 0)
  const stepDone = current.every((q) => done(q, answers[q.id]))
  const last = step === steps.length - 1

  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current) }, [])

  const submit = useMutation({
    mutationFn: () => {
      const payload: SurveyAnswerIn[] = questions.map((q) => {
        const a = answers[q.id]
        return q.answer_type === 'STEPPER'
          ? { question_id: q.id, numeric_value: a?.numeric }
          : { question_id: q.id, selected_option_ids: a?.optionIds ?? [] }
      })
      return surveyApi.submit(templateId, payload)
    },
    onSuccess: () => {
      try { sessionStorage.removeItem(surveyDraftKey(templateId)) } catch { /* ignore */ }
      qc.invalidateQueries({ queryKey: ['me'] })
      qc.invalidateQueries({ queryKey: ['profile'] })
      nav('/', { replace: true })
    },
    onError: (e) => setError(errorMessageWithDetails(e, '제출에 실패했어요.')),
  })

  /** 답을 반영하고, 이 화면의 단일선택 문항이 모두 채워졌으면 잠깐 뒤 자동으로 다음 화면으로 */
  const answer = (q: SurveyQuestion, a: Answer) => {
    const next = { ...answers, [q.id]: a }
    setAnswers(next)
    if (!isSingle(q) || last) return
    if (current.every((cq) => done(cq, next[cq.id]))) {
      if (timer.current) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setStep((s) => Math.min(s + 1, steps.length - 1)), AUTO_ADVANCE_MS)
    }
  }

  return (
    <Screen>
      <TopBar title="실력 설문" back={step === 0 ? '/' : undefined} />
      <div className="h-1.5 bg-line">
        <div className="h-full bg-court-500 transition-all" style={{ width: `${((step + 1) / steps.length) * 100}%` }} />
      </div>
      <Content>
        <p className="text-xs font-semibold text-brand-ink">
          {SECTION_NAME[current[0].section] ?? current[0].section} · {step + 1}/{steps.length}
        </p>
        {current[0].group_label && <h2 className="text-xl font-bold text-ink">{current[0].group_label}</h2>}
        {current.map((q) => (
          <QuestionCard key={q.id} q={q} compact={current.length > 1} answer={answers[q.id]} onChange={(a) => answer(q, a)} />
        ))}
        {error && <Alert>{error}</Alert>}
      </Content>
      <BottomAction>
        <div className="flex gap-2">
          <Button variant="ghost" className="shrink-0 whitespace-nowrap px-4" onClick={() => setStep(step - 1)} disabled={step === 0}>이전</Button>
          {last ? (
            <Button full disabled={!stepDone} loading={submit.isPending} onClick={() => submit.mutate()}>제출하기</Button>
          ) : (
            <Button full disabled={!stepDone} onClick={() => setStep(step + 1)}>다음</Button>
          )}
        </div>
      </BottomAction>
    </Screen>
  )
}

function QuestionCard({ q, answer, onChange, compact }: { q: SurveyQuestion; answer?: Answer; onChange: (a: Answer) => void; compact: boolean }) {
  const picked = answer?.optionIds ?? []
  const multi = q.answer_type === 'MULTI_CHIP'
  const ordered = multi && q.section === 'D' // 가능 포지션: 고른 순서 = 선호 순서
  const chip = multi || q.answer_type === 'SINGLE_CHOICE' || q.answer_type === 'TRIO'
  const toggle = (id: number) =>
    onChange({ optionIds: multi ? (picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]) : [id] })

  return (
    <div className={compact ? 'rounded-2xl border border-line bg-surface p-4' : ''}>
      <h2 className={compact ? 'text-base font-bold text-ink' : 'text-xl font-bold text-ink'}>{q.question_text}</h2>
      {q.help_text && <p className="mt-1 text-sm text-muted">{q.help_text}</p>}
      <div className={`mt-3 ${chip ? 'flex flex-wrap gap-2' : 'space-y-2'}`}>
        {q.answer_type === 'STEPPER' ? (
          <NumberStepper value={answer?.numeric} onChange={(v) => onChange({ optionIds: [], numeric: v })} />
        ) : (
          q.options.map((o, i) => {
            const on = picked.includes(o.id)
            const rank = ordered ? picked.indexOf(o.id) + 1 : 0
            return chip ? (
              <button
                key={o.id}
                type="button"
                onClick={() => toggle(o.id)}
                aria-pressed={on}
                className={`relative min-h-11 rounded-full border px-4 text-sm font-semibold ${on ? 'border-brand bg-brand text-on-brand' : 'border-line-strong bg-surface text-ink'}`}
              >
                {rank > 0 && <span className="absolute -left-1.5 -top-1.5 flex size-5 items-center justify-center rounded-full bg-navy-800 text-[11px] font-bold text-white">{rank}</span>}
                {o.label}
              </button>
            ) : (
              <button
                key={o.id}
                type="button"
                onClick={() => toggle(o.id)}
                className={`block w-full rounded-xl border px-4 py-3.5 text-left text-[15px] ${on ? 'border-court-500 bg-brand-soft font-semibold text-ink' : 'border-line bg-surface text-ink-2'}`}
              >
                <span className="mr-2 text-xs text-faint">{i + 1}</span>{o.label}
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}

/** STEPPER 문항용 (v1 호환. v2 에는 숫자 문항이 없다) */
function NumberStepper({ value, onChange }: { value?: number; onChange: (v: number | undefined) => void }) {
  const v = value ?? 175
  return (
    <div className="flex items-center justify-center gap-4 rounded-2xl border border-line bg-surface py-4">
      <button type="button" aria-label="1 줄이기" onClick={() => onChange(Math.max(120, v - 1))} className="size-12 rounded-xl bg-sunken text-2xl font-bold">−</button>
      <input type="number" inputMode="numeric" aria-label="값" value={value ?? ''} placeholder="175" onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))} className="w-28 bg-transparent text-center text-4xl font-black text-ink outline-none" />
      <button type="button" aria-label="1 늘리기" onClick={() => onChange(Math.min(250, v + 1))} className="size-12 rounded-xl bg-brand-soft text-2xl font-bold text-brand-ink">+</button>
    </div>
  )
}

/* ---------- 팀 가입 직후: 이 동호회에서 내 실력 위치 (구 E3) ---------- */
const LEVELS: SelfRankLevel[] = ['TOP10', 'TOP30', 'MID', 'BOT30', 'BOT10']

export function SelfRankPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const goBack = useGoBack()
  const nav = useNavigate()
  const loc = useLocation()
  // 팀 가입 직후(가입 화면이 이 화면으로 바뀌어 state.from 에 팀이 적혀 있다)면 그 팀으로 — 히스토리를 되감으면 홈으로 가 버린다.
  // 프로필 · 팀 화면에서 왔으면 들어온 화면으로 되감는다. 어느 쪽이든 뒤로가 이 화면으로 돌아오지 않는다
  const from = (loc.state as { from?: string } | null)?.from
  const done = () => (from ? nav(from, { replace: true }) : goBack(`/teams/${id}`))
  const qc = useQueryClient()
  const profile = useQuery({ queryKey: ['profile'], queryFn: surveyApi.myProfile })
  const mine = profile.data?.teams.find((t) => t.team_id === id)
  const [picked, setPicked] = useState<SelfRankLevel | null>(null)
  const m = useMutation({
    mutationFn: (level: SelfRankLevel) => surveyApi.setSelfRank(id, level),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['team', id] }); qc.invalidateQueries({ queryKey: ['me', 'tutorial'] }); done() },  // 시작 안내의 "내 위치" 단계도
    meta: { inlineError: true },
  })
  const current = picked ?? mine?.self_rank_level ?? null

  return (
    <Screen>
      <TopBar title={mine ? mine.team_name : '내 실력 위치'} back={`/teams/${id}`} />
      <div className="h-1.5 bg-line"><div className="h-full w-full bg-court-500" /></div>
      <Content>
        <p className="text-xs font-semibold text-brand-ink">팀 가입 완료 · 마지막 한 문항</p>
        <h2 className="text-xl font-bold text-ink">이 동호회에서 본인의 실력 위치는?</h2>
        <p className="text-sm text-muted">점수가 아니라 이 팀 안에서의 위치예요. 팀 배정 정확도에 가장 큰 영향을 주는 문항이라 팀마다 따로 물어봐요. 나중에 바꿀 수 있어요.</p>
        <div className="space-y-2">
          {LEVELS.map((lv, i) => (
            <button
              key={lv}
              type="button"
              disabled={m.isPending}
              onClick={() => { setPicked(lv); m.mutate(lv) }}
              className={`block w-full rounded-xl border px-4 py-3.5 text-left text-[15px] ${current === lv ? 'border-court-500 bg-brand-soft font-semibold text-ink' : 'border-line bg-surface text-ink-2'}`}
            >
              <span className="mr-2 text-xs text-faint">{i + 1}</span>{SELF_RANK_LABEL[lv]}
            </button>
          ))}
        </div>
        {m.isError && <Alert>{errorMessage(m.error, '저장하지 못했어요.')}</Alert>}
      </Content>
      <BottomAction>
        <Button variant="ghost" full onClick={done}>나중에 할게요</Button>
      </BottomAction>
    </Screen>
  )
}
