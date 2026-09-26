/**
 * 시작 안내(튜토리얼).
 *  - TutorialPrompt: 새 가입자가 홈에 처음 오면 한 번 묻는 팝업. 거절하면 아무 안내도 뜨지 않는다
 *  - TutorialCard  : 홈 맨 위 체크리스트. 며칠 안에 끝나는 준비만 담고, 막힌 단계는 "대기 중" + 이유. × 로 닫으면 끝
 *  - FirstTimeTip  : 배정·경기 기록처럼 나중에 열리는 기능에 처음 들어갔을 때 한 번 뜨는 안내
 * 단계 판정은 서버(GET /me/tutorial)가 실제 데이터로 한다. 문장은 lib/tutorial-content.ts.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { authApi } from '../api/auth'
import { tutorialApi } from '../api/tutorial'
import type { TutorialUpdate, UserDetail } from '../api/types'
import { FLOW, TIPS, type TipId } from '../lib/tutorial-content'
import { Button, Card, Spinner } from './ui'

function useTutorialUpdate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TutorialUpdate) => tutorialApi.update(body),
    onMutate: (body) => {
      // 팝업·안내가 누르는 즉시 사라지도록 내 정보 캐시를 먼저 고친다
      qc.setQueryData<UserDetail>(['me'], (u) => u && {
        ...u,
        ...(body.state ? { tutorial_state: body.state, ...(body.state === 'ACTIVE' && body.path === undefined ? { tutorial_path: null } : {}) } : {}),
        ...(body.path !== undefined ? { tutorial_path: body.path } : {}),
        ...(body.tip_seen ? { tutorial_tips_seen: [...u.tutorial_tips_seen, body.tip_seen] } : {}),
      })
    },
    onSuccess: (v) => { qc.setQueryData(['me', 'tutorial'], v) },
    onSettled: () => { qc.invalidateQueries({ queryKey: ['me'], exact: true }) },
  })
}

/** 새 가입자에게 한 번 — "안내를 받을까요?" */
export function TutorialPrompt({ me }: { me: UserDetail }) {
  const upd = useTutorialUpdate()
  if (me.tutorial_state !== 'PENDING') return null
  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/40 sm:items-center" role="dialog" aria-modal="true" aria-labelledby="tutorial-prompt-title">
      <div className="safe-bottom w-full max-w-md rounded-t-3xl bg-surface p-6 sm:rounded-3xl">
        <div className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-court-500 text-lg font-black text-white" aria-hidden="true">H</div>
        <h2 id="tutorial-prompt-title" className="text-lg font-bold text-ink">처음이시죠?</h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-2">팀에 들어가고 첫 경기를 준비하는 데 필요한 것만 차례로 안내해 드릴게요. 홈 맨 위에 할 일 목록이 생기고, 언제든 닫을 수 있어요.</p>
        <div className="mt-5 space-y-2">
          <Button full loading={upd.isPending && upd.variables?.state === 'ACTIVE'} onClick={() => upd.mutate({ state: 'ACTIVE' })}>안내 받기</Button>
          <Button full variant="ghost" onClick={() => upd.mutate({ state: 'DECLINED' })}>혼자 둘러볼게요</Button>
        </div>
        <p className="mt-3 text-center text-[11px] text-faint">도움말은 내 프로필에서 언제든 볼 수 있어요.</p>
      </div>
    </div>
  )
}

/** 홈 맨 위 체크리스트 카드 */
export function TutorialCard({ me }: { me: UserDetail }) {
  const active = me.tutorial_state === 'ACTIVE'
  const q = useQuery({ queryKey: ['me', 'tutorial'], queryFn: tutorialApi.get, enabled: active })
  const upd = useTutorialUpdate()
  if (!active) return null
  const v = q.data
  const close = (
    <button type="button" onClick={() => upd.mutate({ state: 'CLOSED' })} aria-label="시작 안내 닫기" className="-mr-1.5 -mt-1.5 flex size-9 shrink-0 items-center justify-center rounded-full text-xl text-faint active:bg-sunken">×</button>
  )

  // 경로 선택 — 팀 코드를 받았으면 팀원, 아니면 팀 만들기
  if (!me.tutorial_path) {
    return (
      <Card className="space-y-3 border-brand-line bg-brand-soft">
        <div className="flex items-start justify-between gap-2">
          <div><p className="text-xs font-bold text-brand-ink">시작 안내</p><p className="mt-0.5 font-bold text-ink">팀 코드를 받으셨나요?</p></div>
          {close}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={() => upd.mutate({ path: 'PLAYER' })} className="rounded-xl border border-line bg-surface px-3 py-3 text-left active:bg-sunken">
            <p className="text-sm font-bold text-ink">네, 받았어요</p><p className="text-[11px] text-muted">팀원으로 가입해요</p>
          </button>
          <button type="button" onClick={() => upd.mutate({ path: 'MANAGER' })} className="rounded-xl border border-line bg-surface px-3 py-3 text-left active:bg-sunken">
            <p className="text-sm font-bold text-ink">아니요</p><p className="text-[11px] text-muted">팀을 직접 만들어요</p>
          </button>
        </div>
      </Card>
    )
  }
  if (q.isLoading || !v) return <Card><Spinner /></Card>

  // 다 마침 — 앞으로의 흐름을 한 번 보여 주고 끝
  if (v.all_done) {
    return (
      <Card className="space-y-3 border-brand-line bg-brand-soft">
        <div><p className="text-xs font-bold text-brand-ink">시작 안내 · 준비 끝</p><p className="mt-0.5 font-bold text-ink">이제 이런 순서로 진행돼요</p></div>
        <ol className="space-y-1.5">
          {FLOW[me.tutorial_path].map((line, i) => (
            <li key={line} className="flex gap-2 text-sm text-ink-2"><span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-surface text-[11px] font-bold text-brand-ink">{i + 1}</span><span>{line}</span></li>
          ))}
        </ol>
        <p className="text-[11px] text-muted">그 기능을 처음 열 때 짧은 안내가 한 번 더 떠요.</p>
        <Button full onClick={() => upd.mutate({ state: 'DONE' })}>확인</Button>
      </Card>
    )
  }

  const done = v.steps.filter((s) => s.status === 'DONE').length
  return (
    <Card className="space-y-3 border-brand-line">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold text-brand-ink">시작 안내 · {me.tutorial_path === 'PLAYER' ? '팀원' : '매니저'}</p>
          <p className="mt-0.5 font-bold text-ink">{done}/{v.steps.length} 완료</p>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken"><div className="h-full rounded-full bg-brand transition-all" style={{ width: `${(done / v.steps.length) * 100}%` }} /></div>
        </div>
        {close}
      </div>
      <ol className="space-y-2">
        {v.steps.map((s, i) => (
          <li key={s.key} className={`flex items-start gap-3 rounded-xl px-3 py-2.5 ${s.status === 'TODO' ? 'bg-brand-soft' : 'bg-surface-2'}`}>
            <span className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${s.status === 'DONE' ? 'bg-court-500 text-white' : s.status === 'TODO' ? 'border-2 border-court-500 text-brand-ink' : 'border border-line-strong text-faint'}`}>
              {s.status === 'DONE' ? '✓' : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-semibold ${s.status === 'DONE' ? 'text-muted line-through decoration-faint' : s.status === 'WAITING' ? 'text-muted' : 'text-ink'}`}>
                {s.title}{s.status === 'WAITING' && <span className="ml-1.5 rounded-full bg-sunken px-1.5 py-0.5 text-[10px] font-semibold text-muted no-underline">대기 중</span>}
              </p>
              {s.status !== 'DONE' && <p className="mt-0.5 text-xs text-muted">{s.hint}</p>}
            </div>
            {s.status === 'TODO' && s.link && (
              <Link to={s.link} state={{ from: '/' }} className="flex min-h-9 shrink-0 items-center rounded-lg bg-brand px-3 text-xs font-semibold text-on-brand">{s.action ?? '하기'}</Link>
            )}
          </li>
        ))}
      </ol>
      <p className="text-[11px] text-faint">닫으면 다시 뜨지 않아요. 도움말에서 다시 열 수 있어요.</p>
    </Card>
  )
}

/** 기능을 처음 열었을 때 한 번 — 시작 안내를 받은 사람(ACTIVE·CLOSED·DONE)에게만 */
export function FirstTimeTip({ id }: { id: TipId }) {
  const me = useQuery({ queryKey: ['me'], queryFn: authApi.me })
  const upd = useTutorialUpdate()
  const u = me.data
  if (!u || !['ACTIVE', 'CLOSED', 'DONE'].includes(u.tutorial_state) || u.tutorial_tips_seen.includes(id)) return null
  const t = TIPS[id]
  return (
    <div className="rounded-2xl border border-info-line bg-info-soft px-4 py-3" role="note" aria-label={t.title}>
      <p className="text-sm font-bold text-info-ink">{t.title}</p>
      <ul className="mt-1.5 space-y-1">
        {t.lines.map((l) => <li key={l} className="flex gap-1.5 text-xs leading-relaxed text-ink-2"><span className="text-info-ink" aria-hidden="true">·</span><span>{l}</span></li>)}
      </ul>
      <div className="mt-2.5 flex items-center justify-between">
        <Link to={`/help#${t.help}`} className="text-xs font-semibold text-info-ink underline underline-offset-2">도움말에서 더 보기</Link>
        <button type="button" onClick={() => upd.mutate({ tip_seen: id })} className="min-h-9 rounded-lg bg-surface px-3 text-xs font-semibold text-ink-2 active:bg-sunken">알겠어요</button>
      </div>
    </div>
  )
}
