/**
 * S-16 경기 후 피어 투표 (F9, peer-vote-spec 3.1 · 6절, 이후 사용자 결정 반영).
 * "다음에 같이 뛰고 싶은 사람"만 받는다 — 같은 팀에서 최대 2명, 상대 팀에서 최대 2명 (배정이 없던 회차는 합계 4명).
 * 0명이어도 제출 가능. 이유 칩은 선택한 사람 아래에 인라인.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { eventsApi } from '../api/events'
import { peerApi } from '../api/peer'
import { REASON_TAGS, reasonLabel, type ReasonTag, type VoteCandidate, type VoteIn } from '../api/types'
import { Alert, Avatar, Badge, Button, Card, EmptyState, Spinner } from '../components/ui'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { fmtEvent } from './events'

const MAX_PER_SIDE = 2

export function VotePage() {
  const { eventId } = useParams()
  const id = Number(eventId)
  const nav = useNavigate()
  const qc = useQueryClient()
  const ev = useQuery({ queryKey: ['events', id], queryFn: () => eventsApi.get(id) })
  const t = useQuery({ queryKey: ['events', id, 'vote'], queryFn: () => peerApi.targets(id), retry: false })

  const [picked, setPicked] = useState<number[]>([])
  const [reasons, setReasons] = useState<Record<number, ReasonTag | null>>({})
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})  // 한도까지 고르면 그 팀 목록은 자동으로 접힌다
  const [msg, setMsg] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: (votes: VoteIn[]) => peerApi.submit(id, votes),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['events'] }); qc.invalidateQueries({ queryKey: ['stats'] }) },
    onError: (e) => setMsg(e instanceof ApiError ? e.message : '제출하지 못했어요.'),
  })

  const back = `/events/${id}`
  if (ev.isLoading || t.isLoading) return <Screen><TopBar title="경기 후 투표" back={back} /><Spinner /></Screen>

  // 종료 전 / 비참석자 — 폼을 노출하지 않고 안내만 (스펙 6절)
  if (t.isError) {
    const err = t.error
    const notOpen = err instanceof ApiError && err.code === 'SURVEY_NOT_OPEN'
    return (
      <Screen>
        <TopBar title="경기 후 투표" back={back} />
        <Content>
          <EmptyState
            title={notOpen ? '일정이 끝나면 투표할 수 있어요' : (err instanceof ApiError ? err.message : '투표 명단을 불러오지 못했어요.')}
            desc={notOpen && ev.data ? `${fmtEvent(ev.data)} 종료 후 자동으로 열려요.` : undefined}
            action={<Button variant="ghost" onClick={() => nav(back)}>일정으로 돌아가기</Button>}
          />
        </Content>
      </Screen>
    )
  }
  const data = t.data!
  const byId = new Map(data.candidates.map((c) => [c.player.id, c]))
  const hasTeams = data.candidates.some((c) => c.is_same_team !== null)
  const groups: { key: string; title: string; items: VoteCandidate[] }[] = hasTeams
    ? [
        { key: 'same', title: '우리 팀에서', items: data.candidates.filter((c) => c.is_same_team) },
        { key: 'opp', title: '상대 팀에서', items: data.candidates.filter((c) => c.is_same_team === false) },
        ...(data.candidates.some((c) => c.is_same_team === null) ? [{ key: 'etc', title: '팀 미배정', items: data.candidates.filter((c) => c.is_same_team === null) }] : []),
      ]
    : [{ key: 'all', title: '그날 참석자', items: data.candidates }]
  const limitOf = (key: string) => (key === 'all' || key === 'etc' ? MAX_PER_SIDE * 2 : MAX_PER_SIDE)
  const countIn = (g: { items: VoteCandidate[] }) => g.items.filter((c) => picked.includes(c.player.id)).length

  // 이미 제출 → 완료 화면
  if (data.already_submitted) {
    return (
      <Screen>
        <TopBar title="경기 후 투표" back={back} />
        <Content>
          <Card className="text-center">
            <p className="font-bold text-navy-900">응답을 남겼어요</p>
            <p className="text-xs text-stone-500">투표는 회차당 한 번만 할 수 있어요.</p>
          </Card>
          <section>
            <p className="mb-2 px-1 text-sm font-bold tracking-wide text-stone-500">다음에 같이 뛰고 싶은 사람</p>
            {data.my_votes.length === 0 ? <p className="px-1 text-sm text-stone-400">선택 안 함</p> : (
              <div className="space-y-2">
                {data.my_votes.map((v) => {
                  const c = byId.get(v.target_player_id)
                  return (
                    <Card key={v.target_player_id} className="flex items-center gap-3 py-3">
                      <Avatar name={c?.player.display_name ?? '?'} src={c?.player.profile_image_url} />
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-navy-900">{c?.player.display_name ?? '참가자'}</p>
                        {v.reason_tag && <p className="text-xs text-court-600">{reasonLabel(v.reason_tag, c?.is_same_team ?? null)}</p>}
                      </div>
                      {c && <SquadBadge c={c} />}
                    </Card>
                  )
                })}
              </div>
            )}
          </section>
        </Content>
        <BottomAction><Button variant="secondary" full onClick={() => nav(back)}>일정으로 돌아가기</Button></BottomAction>
      </Screen>
    )
  }

  // 한도까지 고르고 선택한 사람마다 이유까지 정했을 때만 자동으로 접는다 (이유를 고르기 전에 접히지 않게)
  const maybeCollapse = (g: { key: string; items: VoteCandidate[] }, nextPicked: number[], nextReasons: Record<number, ReasonTag | null>) => {
    const mine = g.items.filter((c) => nextPicked.includes(c.player.id)).map((c) => c.player.id)
    if (mine.length >= limitOf(g.key) && mine.every((pid) => nextReasons[pid])) setCollapsed((c) => ({ ...c, [g.key]: true }))
  }
  const toggle = (g: { key: string; items: VoteCandidate[] }, pid: number) => {
    if (picked.includes(pid)) setPicked(picked.filter((x) => x !== pid))
    else if (countIn(g) < limitOf(g.key)) setPicked([...picked, pid])
  }
  const pickReason = (g: { key: string; items: VoteCandidate[] }, pid: number, tag: ReasonTag | null) => {
    const next = { ...reasons, [pid]: tag }
    setReasons(next)
    maybeCollapse(g, picked, next)
  }
  const votes: VoteIn[] = picked.map((pid) => ({ target_player_id: pid, vote_type: 'PLAY_AGAIN' as const, reason_tag: reasons[pid] ?? null }))

  return (
    <Screen>
      <TopBar title="경기 후 투표" back={back} />
      <Content>
        <div className="px-1">
          {ev.data && <p className="text-xs font-semibold text-stone-500">{fmtEvent(ev.data)}</p>}
          <p className="mt-2 text-sm leading-relaxed text-navy-900">같이 농구를 한 사람 중 다음에 같은 팀으로 뛰고 싶은 사람을 골라주세요. {hasTeams ? '우리 팀 최대 2명, 상대 팀 최대 2명까지 고를 수 있어요.' : `최대 ${MAX_PER_SIDE * 2}명까지 고를 수 있어요.`}</p>
        </div>
        {msg && <Alert>{msg}</Alert>}

        {groups.map((g) => (
          <section key={g.key}>
            <div className="mb-2 flex items-center justify-between px-1">
              <h3 className="text-sm font-bold tracking-wide text-stone-500">{g.title}</h3>
              <span className="flex items-center gap-2">
                <span className={`text-xs font-semibold ${countIn(g) ? 'text-court-600' : 'text-stone-400'}`}>{countIn(g)}/{limitOf(g.key)} 선택됨</span>
                {!collapsed[g.key] && countIn(g) > 0 && <button className="text-xs font-semibold text-navy-600" onClick={() => setCollapsed((c) => ({ ...c, [g.key]: true }))}>접기</button>}
              </span>
            </div>
            {collapsed[g.key] ? (
              <Card className="flex items-center gap-3 py-3">
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                  {g.items.filter((c) => picked.includes(c.player.id)).map((c) => (
                    <span key={c.player.id} className="inline-flex items-center gap-1 rounded-full bg-court-50 px-2.5 py-1 text-xs font-semibold text-court-700">
                      {c.player.display_name}{reasons[c.player.id] && <span className="font-normal text-court-500">· {reasonLabel(reasons[c.player.id]!, c.is_same_team)}</span>}
                    </span>
                  ))}
                </div>
                <Button variant="ghost" className="min-h-10 text-sm" onClick={() => setCollapsed((c) => ({ ...c, [g.key]: false }))}>수정</Button>
              </Card>
            ) : (
            <div className="space-y-2">
              {g.items.map((c) => {
                const on = picked.includes(c.player.id)
                return (
                  <div key={c.player.id}>
                    <CandidateRow c={c} on={on} disabled={!on && countIn(g) >= limitOf(g.key)} onClick={() => toggle(g, c.player.id)} />
                    {on && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5 px-2">
                        {REASON_TAGS.map((r) => {
                          const sel = reasons[c.player.id] === r.tag
                          return (
                            <button key={r.tag} onClick={() => pickReason(g, c.player.id, sel ? null : r.tag)}
                              className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${sel ? 'border-court-500 bg-court-500 text-white' : 'border-stone-200 bg-white text-stone-600'}`}>
                              {reasonLabel(r.tag, c.is_same_team)}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            )}
          </section>
        ))}
      </Content>
      <BottomAction>
        <Button full loading={submit.isPending} onClick={() => (votes.length > 0 || confirm('아무도 선택하지 않고 제출할까요? 나중에 다시 할 수 없어요.')) && submit.mutate(votes)}>
          {votes.length === 0 ? '선택 없이 제출' : `${votes.length}명 제출`}
        </Button>
      </BottomAction>
    </Screen>
  )
}

function SquadBadge({ c }: { c: VoteCandidate }) {
  if (c.squad_no === null) return c.player.kind === 'GUEST' ? <Badge>게스트</Badge> : null
  const black = c.squad_no === 1
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${black ? 'bg-navy-900 text-white' : 'border border-stone-300 bg-white text-navy-900'}`}>
      {c.squad_name ?? (black ? '블랙' : '화이트')}
    </span>
  )
}

function CandidateRow({ c, on, disabled, onClick }: { c: VoteCandidate; on: boolean; disabled: boolean; onClick: () => void }) {
  const p = c.player
  return (
    <button onClick={onClick} disabled={disabled} className={`flex min-h-14 w-full items-center gap-3 rounded-2xl border-2 bg-white px-3 py-2 text-left transition disabled:opacity-40 ${on ? 'border-court-500 bg-court-50' : 'border-stone-200'}`}>
      <Avatar name={p.display_name} src={p.profile_image_url} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-navy-900">{p.display_name}{p.kind === 'GUEST' && <span className="ml-1.5 text-[11px] text-stone-500">게스트</span>}</p>
        <p className="truncate text-xs text-stone-500">{p.primary_position ?? p.playable_positions[0] ?? '포지션 미입력'}</p>
      </div>
      <SquadBadge c={c} />
      <span className={`flex size-6 items-center justify-center rounded-full text-xs font-bold ${on ? 'bg-court-500 text-white' : 'border border-stone-300 text-transparent'}`}>✓</span>
    </button>
  )
}
