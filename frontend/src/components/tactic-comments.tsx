/**
 * 전술 댓글 (docs/07 FR-60, S-29 아래). 팀 안에서 전술 하나에 다는 의견 — "2번 코너가 좁아요" 같은 것.
 * 팀원이면 누구나 읽고 쓴다. 지우기는 쓴 사람과 매니저만.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'
import { tacticCommentsApi } from '../api/tactics'
import { Alert, Button, SectionTitle, Spinner } from './ui'

const when = (iso: string) => {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function TacticComments({ teamId, playKey }: { teamId: number; playKey: string }) {
  const qc = useQueryClient()
  const key = ['tactics', 'comments', teamId, playKey]
  const list = useQuery({ queryKey: key, queryFn: () => tacticCommentsApi.list(teamId, playKey), retry: false })
  const [text, setText] = useState('')
  const add = useMutation({
    mutationFn: () => tacticCommentsApi.add(teamId, playKey, text),
    onSuccess: () => { setText(''); qc.invalidateQueries({ queryKey: key }) },
  })
  const remove = useMutation({
    mutationFn: (id: number) => tacticCommentsApi.remove(teamId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  })
  if (list.error instanceof ApiError && list.error.status === 403) return null // 팀원이 아니면 숨긴다
  const items = list.data?.items ?? []
  return (
    <section aria-label="전술 댓글">
      <SectionTitle>댓글 {items.length > 0 && <span className="font-normal text-muted">{items.length}</span>}</SectionTitle>
      {list.isLoading ? <Spinner /> : (
        <div className="space-y-2">
          {items.length === 0 && <p className="px-1 text-sm text-muted">아직 댓글이 없어요. 이 전술을 써 보고 느낀 점을 남겨 주세요.</p>}
          {items.map((c) => (
            <div key={c.id} className="rounded-2xl border border-line bg-surface px-4 py-3">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-bold text-ink">{c.author_name}{c.mine && <span className="ml-1 font-normal text-muted">(나)</span>}</span>
                <span className="text-faint">{when(c.created_at)}</span>
                {c.can_delete && (
                  <button
                    type="button" onClick={() => remove.mutate(c.id)} disabled={remove.isPending}
                    className="ml-auto min-h-8 px-2 text-xs text-muted active:text-danger-ink" aria-label={`${c.author_name}의 댓글 지우기`}
                  >
                    지우기
                  </button>
                )}
              </div>
              <p className="mt-1 whitespace-pre-line break-words text-sm text-ink-2">{c.body}</p>
            </div>
          ))}
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate() }}
          >
            <label className="sr-only" htmlFor="tactic-comment">댓글</label>
            <textarea
              id="tactic-comment" value={text} onChange={(e) => setText(e.target.value.slice(0, 500))} rows={2}
              placeholder="이 전술에 대한 의견" className="min-h-11 flex-1 resize-none rounded-xl border border-line bg-surface px-3 py-2.5 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
            />
            <Button type="submit" loading={add.isPending} disabled={!text.trim()} className="shrink-0">남기기</Button>
          </form>
          {add.isError && <Alert>{add.error instanceof ApiError ? add.error.message : '댓글을 남기지 못했어요.'}</Alert>}
        </div>
      )}
    </section>
  )
}
