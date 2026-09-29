/**
 * 배정 설명 카드 (docs/07 FR-51, S-13 · S-14). 규칙 설명 카드를 대신한다.
 *
 * 화면에 들어오면 바로 AI 설명을 불러와 한 글자씩 보여 준다(useTypewriter). 판단(누가 활약할지 · 누구와 호흡이 좋을지 ·
 * 어떤 역할이 부족한지 · 왜 그 포지션인지)은 서버가 규칙으로 했고 AI 는 문장만 쓴다.
 * AI 를 쓸 수 없거나 실패하면 같은 자리에 기존 규칙 설명(fallbackText)을 "AI" 표시 없이 보여 준다.
 */
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { assignmentsApi } from '../api/assignments'
import { useDebounced, useTypewriter } from '../lib/typewriter'
import { Card } from './ui'

const AI_NOTE = 'AI가 쓴 설명이에요 · 팀은 배정 알고리즘이 나눴어요'

function Frame({ ai, title, children }: { ai: boolean; title: string; children: ReactNode }) {
  return (
    <Card className="space-y-2.5 py-3.5">
      <div className="flex items-center gap-2">
        {ai && <span className="flex h-5 items-center rounded-full bg-brand-soft px-1.5 text-[10px] font-black text-brand-ink" aria-hidden="true">AI</span>}
        <p className="text-sm font-bold text-ink">{title}</p>
      </div>
      {children}
    </Card>
  )
}

export function Thinking({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="flex gap-0.5" aria-hidden="true">
        {[0, 150, 300].map((d) => <span key={d} className="size-1.5 animate-bounce rounded-full bg-brand" style={{ animationDelay: `${d}ms` }} />)}
      </span>
      {label}
    </p>
  )
}

function Caret({ on }: { on: boolean }) {
  return on ? <span className="ml-0.5 inline-block h-3.5 w-[2px] animate-pulse bg-brand align-middle" aria-hidden="true" /> : null
}

function Fallback({ title, text }: { title: string; text: string | null | undefined }) {
  return (
    <Frame ai={false} title={title}>
      <p className="whitespace-pre-line text-sm text-ink-2">{text || '설명을 불러오지 못했어요.'}</p>
    </Frame>
  )
}

/** 항목 목록을 섹션별로 타이핑. 섹션 제목은 그 섹션 첫 글자가 나올 때 함께 뜬다 */
export function TypedSections({ sections, note = true }: { sections: { title?: string; items: string[]; tone?: 'lead' | 'warn' }[]; note?: boolean }) {
  const flat = sections.flatMap((s) => s.items)
  const [typed, done] = useTypewriter(flat)
  const lastIdx = typed.reduce((acc, t, k) => (t ? k : acc), 0)
  const starts = sections.map((_, si) => sections.slice(0, si).reduce((a, x) => a + x.items.length, 0))
  return (
    <div className="space-y-2.5">
      {sections.map((s, si) => {
        const start = starts[si]
        const shown = typed.slice(start, start + s.items.length)
        if (!shown.some(Boolean)) return null
        return (
          <div key={si} className={s.tone === 'warn' ? 'rounded-xl bg-warn-soft px-3 py-2' : ''}>
            {s.title && <p className={`mb-1 text-xs font-bold ${s.tone === 'warn' ? 'text-warn-ink' : 'text-muted'}`}>{s.title}</p>}
            {s.tone === 'lead' ? (
              <p className="text-[15px] font-semibold leading-snug text-ink">{shown[0]}<Caret on={!done && lastIdx === start} /></p>
            ) : (
              <ul className="space-y-1">
                {shown.map((t, k) => t && (
                  <li key={k} className={`flex gap-1.5 text-sm ${s.tone === 'warn' ? 'text-warn-ink' : 'text-ink-2'}`}>
                    {s.tone !== 'warn' && <span className="text-brand-ink" aria-hidden="true">·</span>}
                    <span>{t}<Caret on={!done && lastIdx === start + k} /></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
      {done && note && <p className="text-[11px] text-faint">{AI_NOTE}</p>}
    </div>
  )
}

/** 매니저용 — 후보안 하나. rosterKey 는 명단이 바뀌면 달라지는 값. 선수를 옮기는 동안은 멈췄다가 1.2초 뒤에 새로 부른다 */
export function AiExplainCard({ candidateId, rosterKey, fallbackText }: { candidateId: number; rosterKey: string; fallbackText: string | null }) {
  const settled = useDebounced(rosterKey, 1200)
  const q = useQuery({
    queryKey: ['ai', 'explain', candidateId, settled],
    queryFn: () => assignmentsApi.aiExplanation(candidateId),
    staleTime: Infinity, retry: false,
  })
  const d = q.data
  if (q.isError || (d && d.fallback)) return <Fallback title="이렇게 나눈 이유" text={d?.text ?? fallbackText} />
  if (!d || settled !== rosterKey) {
    return <Frame ai title="AI 배정 설명"><Thinking label={settled !== rosterKey ? '바뀐 구성으로 다시 읽고 있어요…' : 'AI가 두 팀을 읽고 있어요…'} /></Frame>
  }
  return (
    <Frame ai title="AI 배정 설명">
      <TypedSections sections={[
        { items: [d.summary], tone: 'lead' },
        { title: '활약이 기대돼요', items: d.key_players },
        { title: '호흡이 좋을 조합', items: d.chemistry },
        { title: '부족한 역할', items: d.gaps },
        { title: '경기 중 확인할 점', items: d.watch_point ? [d.watch_point] : [], tone: 'warn' },
      ]} />
    </Frame>
  )
}

/** 팀원용 — 나에게 맞춘 안내 (왜 이 포지션 · 기대 역할 · 호흡 맞출 동료) */
export function AiMessageCard({ eventId, fallbackText }: { eventId: number; fallbackText: string | null }) {
  const q = useQuery({
    queryKey: ['ai', 'message', eventId],
    queryFn: () => assignmentsApi.aiMessage(eventId),
    staleTime: 5 * 60_000, retry: false,
  })
  const d = q.data
  if (d && !d.in_assignment) return null
  if (q.isError || (d && d.fallback)) return <Fallback title="오늘 배정" text={d?.text ?? fallbackText} />
  if (!d) return <Frame ai title="AI 한마디"><Thinking label="AI가 오늘 내 역할을 정리하고 있어요…" /></Frame>
  return (
    <Frame ai title="AI 한마디">
      <TypedSections sections={[
        { title: '왜 이 포지션일까요', items: [d.why_position].filter(Boolean) },
        { title: '오늘 기대하는 역할', items: [d.role].filter(Boolean) },
        { title: '호흡을 맞춰 보세요', items: [d.partner].filter(Boolean) },
      ]} />
    </Frame>
  )
}
