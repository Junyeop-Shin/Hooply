/**
 * AI 배정 설명 카드 (docs/07 FR-51, S-13 · S-14).
 *
 * 둘 다 접힌 채로 시작하고, **펼칠 때만** 서버를 부른다 (확정할 때 자동 호출 없음 — FR-50).
 * 판단은 배정 알고리즘이 했고 AI 는 문장만 쓴다. AI 가 실패하거나 키가 없으면 서버가 기존 규칙 설명을 주고(fallback),
 * 그 설명은 카드 바로 위에 이미 있으므로 같은 글을 되풀이하지 않고 한 줄로 알린다.
 */
import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { assignmentsApi } from '../api/assignments'
import { Card } from './ui'

function Collapsible({ title, desc, open, onToggle, children }: { title: string; desc: string; open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <Card className="space-y-2 py-3">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-2 text-left">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-black text-brand-ink" aria-hidden="true">AI</span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-ink">{title}</span>
          {!open && <span className="block text-xs text-muted">{desc}</span>}
        </span>
        <span className="text-faint" aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && children}
    </Card>
  )
}

function Loading() {
  return (
    <p className="flex items-center gap-2 text-sm text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-line border-t-brand" />AI가 설명을 쓰고 있어요…
    </p>
  )
}

const errText = (e: unknown) => (e instanceof ApiError ? e.message : '설명을 불러오지 못했어요.')
const AI_NOTE = 'AI가 만든 설명이에요 · 팀은 배정 알고리즘이 나눴어요'
const FALLBACK_NOTE = '지금은 AI 설명을 만들 수 없어 위의 기본 설명으로 대신해요.'

/** 매니저용 — 후보안 하나. rosterKey 는 명단이 바뀌면 달라지는 값 (선수를 옮기면 새로 부르게) */
export function AiExplainCard({ candidateId, rosterKey }: { candidateId: number; rosterKey: string }) {
  const [open, setOpen] = useState(false)
  const q = useQuery({
    queryKey: ['ai', 'explain', candidateId, rosterKey],
    queryFn: () => assignmentsApi.aiExplanation(candidateId),
    enabled: open, staleTime: Infinity, retry: false,
  })
  const d = q.data
  return (
    <Collapsible title="AI 배정 설명" desc="이 배정의 근거를 문장으로 정리해 줘요" open={open} onToggle={() => setOpen(!open)}>
      {q.isLoading ? <Loading /> : q.isError ? <p className="text-sm text-danger-ink">{errText(q.error)}</p> : d && (
        d.fallback ? (
          <p className="text-sm text-muted">{FALLBACK_NOTE}</p>
        ) : (
          <div className="space-y-2">
            <p className="text-sm font-semibold text-ink">{d.summary}</p>
            <ul className="space-y-1">
              {d.reasons.map((r) => <li key={r} className="flex gap-1.5 text-sm text-ink-2"><span className="text-brand-ink" aria-hidden="true">·</span>{r}</li>)}
            </ul>
            {d.watch_point && (
              <p className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn-ink"><b>경기 중 확인할 점</b> · {d.watch_point}</p>
            )}
            <p className="text-[11px] text-faint">{AI_NOTE}</p>
          </div>
        )
      )}
    </Collapsible>
  )
}

/** 팀원용 — 나에게 맞춘 한마디 */
export function AiMessageCard({ eventId }: { eventId: number }) {
  const [open, setOpen] = useState(false)
  const q = useQuery({
    queryKey: ['ai', 'message', eventId],
    queryFn: () => assignmentsApi.aiMessage(eventId),
    enabled: open, staleTime: 5 * 60_000, retry: false,
  })
  const d = q.data
  return (
    <Collapsible title="AI 한마디" desc="오늘 내 자리와 팀을 짧게 알려 줘요" open={open} onToggle={() => setOpen(!open)}>
      {q.isLoading ? <Loading /> : q.isError ? <p className="text-sm text-danger-ink">{errText(q.error)}</p> : d && (
        d.message === null ? <p className="text-sm text-muted">이번 배정에는 내 자리가 없어요.</p>
          : d.fallback ? <p className="text-sm text-muted">{FALLBACK_NOTE}</p>
          : (
            <div className="space-y-1.5">
              <p className="text-sm text-ink-2">{d.message}</p>
              <p className="text-[11px] text-faint">{AI_NOTE}</p>
            </div>
          )
      )}
    </Collapsible>
  )
}
