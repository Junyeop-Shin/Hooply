/**
 * S-19 매니저 실력 정렬 (F14, 8.5절). 팀원 카드를 실력 순서로 늘어놓고 저장하면 새 버전이 쌓인다.
 * 드래그(HTML5 DnD)와 ↑↓ 버튼 둘 다 지원 — 모바일에서는 버튼이 확실하다.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { rankingsApi } from '../api/assignments'
import { teamsApi } from '../api/teams'
import type { PlayerCard } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, GradeDot, Spinner } from '../components/ui'
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
    onError: (e) => setMsg(e instanceof ApiError ? e.message : '저장하지 못했어요.'),
  })

  const move = (i: number, j: number) => {
    if (!order || j < 0 || j >= order.length) return
    const next = [...order]
    const [item] = next.splice(i, 1)
    next.splice(j, 0, item)
    setOrder(next)
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
        {!order ? <Spinner /> : (
          <div className="space-y-1.5">
            {order.map((p, i) => (
              <Card
                key={p.id}
                className={`flex items-center gap-2 py-2 ${drag === i ? 'opacity-50' : ''}`}
                onClick={undefined}
              >
                <div
                  draggable
                  onDragStart={() => setDrag(i)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => { if (drag !== null) move(drag, i); setDrag(null) }}
                  onDragEnd={() => setDrag(null)}
                  className="flex min-w-0 flex-1 cursor-grab items-center gap-2 active:cursor-grabbing"
                >
                  <span className="w-6 text-center text-sm font-black text-brand-ink">{i + 1}</span>
                  <Avatar name={p.display_name} src={p.profile_image_url} size="sm" />
                  <span className="truncate font-semibold text-ink">{p.display_name}</span>
                  {p.kind === 'GUEST' && <Badge>게스트</Badge>}
                  <span className="ml-auto text-[11px] text-faint">{p.primary_position ?? ''}</span>
                  <GradeDot grade={p.skill_grade} />
                </div>
                <button onClick={() => move(i, i - 1)} disabled={i === 0} className="size-9 rounded-lg bg-sunken font-bold disabled:opacity-30">↑</button>
                <button onClick={() => move(i, i + 1)} disabled={i === order.length - 1} className="size-9 rounded-lg bg-sunken font-bold disabled:opacity-30">↓</button>
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
