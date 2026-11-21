/**
 * S-19 매니저 실력 정렬 (F14, 8.5절). 팀원 카드를 실력 순서로 늘어놓고 저장하면 새 버전이 쌓인다.
 * 세 가지로 옮긴다: 카드를 눌러 집고 놓을 자리의 카드를 누르기(휴대폰) · ↑↓ 한 칸씩 · 끌어 놓기(데스크톱 HTML5 DnD).
 * 지난 정렬 뒤에 들어온 사람은 "아직 순서 없음" 에 따로 두고, 순서에 넣은 사람만 저장한다 — 맨 뒤에 붙여 저장하면
 * 꼴찌 순위가 사전값의 절반이 된다 (8.5절 "신규 가입자는 다음 정렬 때 편입", docs/09 3-6).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { errorMessage } from '../api/client'
import { confirm, toast } from '../store/feedback'
import { moveItem, tapReorder } from '../lib/reorder'
import { rankingsApi } from '../api/assignments'
import { teamsApi } from '../api/teams'
import type { PlayerCard, RankingView } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, GradeDot, LoadError, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar, useGoBack } from '../components/layout'

/** 정렬 버전의 순서를 지금 팀원에 맞춘다: 그 버전에 있던 사람은 순서대로, 없던 사람은 "아직 순서 없음".
 * 버전이 없으면(처음 정렬) 모두 실력순 한 줄로 */
function splitByVersion(all: PlayerCard[], version: RankingView | undefined) {
  const byId = new Map(all.map((p) => [p.id, p]))
  const ranked = version?.entries.map((e) => e.player.id) ?? []
  const first = ranked.map((pid) => byId.get(pid)).filter((p): p is PlayerCard => !!p)
  const rest = all.filter((p) => !ranked.includes(p.id))
  return first.length === 0 ? { order: rest, unranked: [] } : { order: first, unranked: rest }
}

export function RankingPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const goBack = useGoBack()
  const qc = useQueryClient()
  const players = useQuery({ queryKey: ['team', id, 'players', 'skill'], queryFn: () => teamsApi.players(id, 'skill') })
  const latest = useQuery({ queryKey: ['team', id, 'ranking'], queryFn: () => rankingsApi.latest(id), retry: false })
  const history = useQuery({ queryKey: ['team', id, 'ranking', 'history'], queryFn: () => rankingsApi.history(id), retry: false })
  const [order, setOrder] = useState<PlayerCard[] | null>(null)
  const [unranked, setUnranked] = useState<PlayerCard[]>([])  // 지난 정렬 뒤에 들어온 사람 — 넣기 전까지 저장하지 않는다
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null)  // 불러온 지난 버전 id
  const [drag, setDrag] = useState<number | null>(null)
  const [picked, setPicked] = useState<number | null>(null)  // 눌러서 집은 카드 (휴대폰)
  const [dirty, setDirty] = useState(false)  // 순서를 바꿨는지 — 저장하지 않고 나갈 때 묻는다

  // 초기 순서: 활성 정렬이 있으면 그 순서(+ 새로 들어온 사람은 따로), 없으면 실력순
  useEffect(() => {
    if (order || !players.data || latest.isLoading) return
    const split = splitByVersion(players.data.items, latest.data)
    setOrder(split.order); setUnranked(split.unranked)
  }, [players.data, latest.data, latest.isLoading, order])

  const save = useMutation({
    mutationFn: () => rankingsApi.create(id, order!.map((p) => p.id)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['team', id] }); qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['stats'] }); goBack(`/teams/${id}/members`) },
    onError: (e) => toast(errorMessage(e, '저장하지 못했어요.'), 'error'),
  })

  const include = (p: PlayerCard) => {
    setOrder((o) => [...(o ?? []), p]); setUnranked((u) => u.filter((x) => x.id !== p.id)); setPicked(null); setDirty(true)
  }
  const loadVersion = async (v: RankingView) => {
    if (dirty && !(await confirm({ title: '지난 순서를 불러올까요?', body: '지금 바꾼 순서는 사라져요. 저장하기 전까지는 반영되지 않아요.', confirmLabel: '불러오기' }))) return
    const split = splitByVersion(players.data?.items ?? [], v)
    setOrder(split.order); setUnranked(split.unranked); setPicked(null); setLoadedFrom(v.id); setDirty(true)
  }
  const older = (history.data?.items ?? []).filter((v) => !v.is_active).slice(0, 5)
  const fmtDate = (iso: string) => `${new Date(iso).getMonth() + 1}/${new Date(iso).getDate()}`

  const move = (i: number, j: number) => {
    if (!order || j < 0 || j >= order.length) return
    setOrder(moveItem(order, i, j)); setPicked(null); setDirty(true)
  }
  const tap = (i: number) => {
    if (!order) return
    const next = tapReorder({ order, picked }, i)
    setOrder(next.order); setPicked(next.picked); if (next.order !== order) setDirty(true)
  }

  return (
    <Screen>
      <TopBar title="실력 정렬" back={`/teams/${id}`} beforeBack={async () => !dirty || confirm({ title: '저장하지 않고 나갈까요?', body: '바꾼 순서가 사라져요.', confirmLabel: '나가기', cancelLabel: '계속 정렬', danger: true })} />
      <Content>
        <Alert kind="info">
          잘하는 사람이 <b>위</b>로 오게 놓아 주세요. 설문과 반반 섞여 처음 실력이 되고, 저장한 순서는 남아서 아래 "지난 순서"에서 다시 불러올 수 있어요.
          {latest.data && <span className="mt-1 block text-xs text-muted">지금 쓰는 순서는 {fmtDate(latest.data.ranked_at)}에 저장했어요.</span>}
        </Alert>
        {older.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 px-1 text-xs text-muted">
            <span>지난 순서</span>
            {older.map((v) => (
              <button key={v.id} onClick={() => loadVersion(v)} aria-pressed={loadedFrom === v.id} className={`min-h-11 rounded-full px-1 ${loadedFrom === v.id ? 'font-bold text-brand-ink' : 'font-semibold text-ink-2'}`}>
                <span className="rounded-full border border-line px-2.5 py-1">{fmtDate(v.ranked_at)} 순서</span>
              </button>
            ))}
          </div>
        )}
        {loadedFrom !== null && <p className="px-1 text-xs text-brand-ink">지난 순서를 불러왔어요. "이 순서로 저장"을 눌러야 반영돼요.</p>}
        {/* 집은 상태를 알리는 한 줄 — 화면을 내려도 보이게 위에 붙여 둔다 */}
        {order && (
          <p className="sticky top-14 z-[5] -mx-1 rounded-xl bg-canvas/95 px-2 py-1.5 text-xs text-muted" aria-live="polite">
            {picked !== null
              ? <><b className="text-brand-ink">{order[picked].display_name}</b>님을 집었어요. 놓을 자리의 카드를 눌러 주세요. 다시 누르면 내려놓아요.</>
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
                  <span className="ml-auto text-[11px] text-muted">{p.primary_position ?? ''}</span>
                  <GradeDot grade={p.skill_grade} />
                </div>
                <button onClick={() => move(i, i - 1)} disabled={i === 0} aria-label={`${p.display_name} 한 칸 위로`} className="size-11 shrink-0 rounded-lg bg-sunken font-bold disabled:opacity-30">↑</button>
                <button onClick={() => move(i, i + 1)} disabled={i === order.length - 1} aria-label={`${p.display_name} 한 칸 아래로`} className="size-11 shrink-0 rounded-lg bg-sunken font-bold disabled:opacity-30">↓</button>
              </Card>
            ))}
          </div>
        )}
        {order && unranked.length > 0 && (
          <section className="space-y-1.5">
            <p className="px-1 pt-2 text-sm font-bold text-ink">아직 순서 없음 {unranked.length}</p>
            <p className="px-1 text-xs text-muted">지난 정렬 뒤에 들어온 사람이에요. 넣으면 맨 아래로 들어가니 자리로 옮겨 주세요. 넣지 않으면 설문 결과만으로 실력이 정해져요.</p>
            {unranked.map((p) => (
              <Card key={p.id} className="flex items-center gap-2 border-dashed py-2">
                <Avatar name={p.display_name} src={p.profile_image_url} size="sm" />
                <span className="min-w-0 flex-1 truncate font-semibold text-ink">{p.display_name}</span>
                {p.kind === 'GUEST' && <Badge>게스트</Badge>}
                <GradeDot grade={p.skill_grade} />
                <Button variant="secondary" className="shrink-0 px-3 text-xs" onClick={() => include(p)}>순서에 넣기</Button>
              </Card>
            ))}
          </section>
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
