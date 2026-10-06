/**
 * S-19 매니저 실력 정렬 (F14, 8.5절). 팀원 카드를 실력 순서로 늘어놓고 저장하면 새 버전이 쌓인다.
 * 세 가지로 옮긴다: 카드를 눌러 집고 놓을 자리의 카드를 누르기(휴대폰) · ↑↓ 한 칸씩 · 끌어 놓기(데스크톱 HTML5 DnD).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { moveItem, tapReorder } from '../lib/reorder'
import { rankingsApi } from '../api/assignments'
import { teamsApi } from '../api/teams'
import type { PlayerCard } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, GradeDot, LoadError, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar, useGoBack } from '../components/layout'

export function RankingPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const goBack = useGoBack()
  const qc = useQueryClient()
  const players = useQuery({ queryKey: ['team', id, 'players', 'skill'], queryFn: () => teamsApi.players(id, 'skill') })
  const latest = useQuery({ queryKey: ['team', id, 'ranking'], queryFn: () => rankingsApi.latest(id), retry: false })
  const [order, setOrder] = useState<PlayerCard[] | null>(null)
  const [drag, setDrag] = useState<number | null>(null)
  const [picked, setPicked] = useState<number | null>(null)  // 눌러서 집은 카드 (휴대폰)
  const [msg, setMsg] = useState<string | null>(null)

  // 초기 순서: 활성 정렬이 있으면 그 순서(+ 새로 들어온 사람은 뒤에), 없으면 실력순
  useEffect(() => {
    if (order || !players.data || latest.isLoading) return
    const all = players.data.items
    const ranked = latest.data?.entries.map((e) => e.player.id) ?? []
    const byId = new Map(all.map((p) => [p.id, p]))
    const first = ranked.map((pid) => byId.get(pid)).filter((p): p is PlayerCard => !!p)
    const rest = all.filter((p) => !ranked.includes(p.id))
    setOrder([...first, ...rest])
  }, [players.data, latest.data, latest.isLoading, order])

  const save = useMutation({
    mutationFn: () => rankingsApi.create(id, order!.map((p) => p.id)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['team', id] }); qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['stats'] }); goBack(`/teams/${id}/members`) },
    onError: (e) => setMsg(errorMessage(e, '저장하지 못했어요.')),
  })

  const move = (i: number, j: number) => {
    if (!order || j < 0 || j >= order.length) return
    setOrder(moveItem(order, i, j)); setPicked(null)
  }
  const tap = (i: number) => {
    if (!order) return
    const next = tapReorder({ order, picked }, i)
    setOrder(next.order); setPicked(next.picked)
  }

  return (
    <Screen>
      <TopBar title="실력 정렬" back={`/teams/${id}`} />
      <Content>
        <Alert kind="info">
          잘하는 사람이 <b>위</b>로 오게 놓아 주세요. 설문과 반반 섞여 처음 실력이 되고, 저장본은 남아서 되돌릴 수 있어요.
          {latest.data && <span className="mt-1 block text-xs text-muted">지금 쓰는 순서: {new Date(latest.data.ranked_at).toLocaleDateString('ko-KR')} 저장본</span>}
        </Alert>
        {msg && <Alert>{msg}</Alert>}
        {/* 집은 상태를 알리는 한 줄 — 화면을 내려도 보이게 위에 붙여 둔다 */}
        {order && (
          <p className="sticky top-14 z-[5] -mx-1 rounded-xl bg-canvas/95 px-2 py-1.5 text-xs text-muted" aria-live="polite">
            {picked !== null
              ? <><b className="text-brand-ink">{order[picked].display_name}</b>님을 집었어요. 놓을 자리의 카드를 누르세요. 다시 누르면 취소돼요.</>
              : '카드를 누르면 집어요. 그다음 놓을 자리를 누르면 옮겨져요.'}
          </p>
        )}
        {!order && players.isError ? <LoadError message={errorMessage(players.error, '팀원을 불러오지 못했어요.')} onRetry={() => players.refetch()} retrying={players.isFetching} /> : !order ? <Spinner page /> : (
          <div className="space-y-1.5">
            {order.map((p, i) => (
              <Card
                key={p.id}
                className={`flex items-center gap-2 py-2 ${drag === i ? 'opacity-50' : ''} ${picked === i ? 'border-brand bg-brand-soft ring-2 ring-brand-line' : picked !== null ? 'border-dashed' : ''}`}
              >
                <div
                  role="button" tabIndex={0}
                  aria-pressed={picked === i}
                  aria-label={picked === null ? `${i + 1}위 ${p.display_name} 집기` : picked === i ? `${p.display_name} 내려놓기` : `${p.display_name} 자리(${i + 1}위)에 놓기`}
                  onClick={() => tap(i)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tap(i) } }}
                  draggable
                  onDragStart={() => { setDrag(i); setPicked(null) }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => { if (drag !== null) move(drag, i); setDrag(null) }}
                  onDragEnd={() => setDrag(null)}
                  className="flex min-h-11 min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-lg focus-visible:outline-2 focus-visible:outline-brand"
                >
                  <span className="w-6 text-center text-sm font-black text-brand-ink">{i + 1}</span>
                  <Avatar name={p.display_name} src={p.profile_image_url} size="sm" />
                  <span className="truncate font-semibold text-ink">{p.display_name}</span>
                  {p.kind === 'GUEST' && <Badge>게스트</Badge>}
                  <span className="ml-auto text-[11px] text-faint">{p.primary_position ?? ''}</span>
                  <GradeDot grade={p.skill_grade} />
                </div>
                <button onClick={() => move(i, i - 1)} disabled={i === 0} aria-label={`${p.display_name} 한 칸 위로`} className="size-11 shrink-0 rounded-lg bg-sunken font-bold disabled:opacity-30">↑</button>
                <button onClick={() => move(i, i + 1)} disabled={i === order.length - 1} aria-label={`${p.display_name} 한 칸 아래로`} className="size-11 shrink-0 rounded-lg bg-sunken font-bold disabled:opacity-30">↓</button>
              </Card>
            ))}
          </div>
        )}
      </Content>
      <BottomAction>
        <Button full loading={save.isPending} disabled={!order || order.length < 2} onClick={() => save.mutate()}>
          이 순서로 저장
        </Button>
      </BottomAction>
    </Screen>
  )
}
