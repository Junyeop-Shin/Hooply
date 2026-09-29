/**
 * S-29 전술판 (docs/07 FR-47). 경로: /tactics/:key?event=일정&squad=팀번호&fill=선수id,…
 *
 * - `event` 가 없으면 전술 설명만 (전술 탭 목록에서 들어온 경우).
 * - `event` 가 있으면 그날 블랙/화이트 이름표를 함께 보여 준다. 참석자는 보기만, 매니저는 동그라미를 눌러 고르고 저장한다.
 * - `fill` 은 추천 카드에서 넘긴 슬롯 순서대로의 선수 id. 매니저 화면에서 저장 전 초안으로 채워 둔다.
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { tacticsApi } from '../api/tactics'
import type { EventPlayView, Play, SquadTags } from '../api/types'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { TacticBoard, type BoardTone } from '../components/tactic-board'
import { Alert, Badge, Button, Card, Spinner } from '../components/ui'
import { DEFENSE_LABEL, ROLE_LABEL } from '../lib/tactics'

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)
const CIRCLED = ['①', '②', '③', '④', '⑤']
const toneOf = (squadNo: number): BoardTone => (squadNo === 1 ? 'black' : 'white')

type Draft = Record<number, (number | null)[]> // squad_no → 슬롯 1~5 의 player_id

function draftFrom(view: EventPlayView): Draft {
  const out: Draft = {}
  for (const sq of view.squads) {
    const row: (number | null)[] = [null, null, null, null, null]
    for (const s of sq.slots) row[s.slot - 1] = s.player_id
    out[sq.squad_no] = row
  }
  return out
}

export function TacticBoardPage() {
  const { key = '' } = useParams()
  const [sp] = useSearchParams()
  const eventId = Number(sp.get('event')) || null
  const playKey = `preset:${key}`
  const presets = useQuery({ queryKey: ['tactics', 'presets'], queryFn: tacticsApi.presets, staleTime: Infinity })
  const view = useQuery({
    queryKey: ['tactics', 'event', eventId, playKey], queryFn: () => tacticsApi.play(eventId!, playKey), enabled: eventId !== null,
    retry: false,
  })
  const play: Play | undefined = view.data?.play ?? presets.data?.items.find((p) => p.key === key)

  if (!play) {
    return (
      <Screen>
        <TopBar title="전술" back="/" />
        {presets.isLoading || view.isLoading ? <Spinner /> : <Content><Alert>없는 전술이에요.</Alert></Content>}
      </Screen>
    )
  }
  const withTags = view.data && view.data.squads.length > 0 ? view.data : null
  return withTags ? <EventBoard play={play} view={withTags} eventId={eventId!} /> : <PlainBoard play={play} note={view.isError ? errMsg(view.error, '') : null} />
}

function PlayHeader({ play }: { play: Play }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-bold text-ink">{play.name}</h2>
        <Badge tone={play.defense === 'zone' ? 'navy' : 'neutral'}>{DEFENSE_LABEL[play.defense]}</Badge>
      </div>
      <p className="text-sm text-muted">{play.summary}</p>
    </div>
  )
}

function RoleList({ play, names, onTap }: { play: Play; names?: (string | null)[]; onTap?: (slot: number) => void }) {
  return (
    <Card className="divide-y divide-line p-0">
      {play.roles.map((role, i) => {
        const inner = (
          <>
            <span className="w-6 text-base font-bold text-brand-ink">{CIRCLED[i]}</span>
            <span className="w-24 text-sm text-ink-2">{ROLE_LABEL[role]}</span>
            <span className={`flex-1 truncate text-sm ${names?.[i] ? 'font-semibold text-ink' : 'text-faint'}`}>
              {names ? names[i] ?? (onTap ? '눌러서 고르기' : '비어 있음') : ''}
            </span>
            {onTap && <span className="text-faint" aria-hidden="true">›</span>}
          </>
        )
        return onTap ? (
          <button key={i} type="button" onClick={() => onTap(i + 1)} className="flex min-h-11 w-full items-center gap-2 px-4 text-left active:bg-sunken">{inner}</button>
        ) : (
          <div key={i} className="flex min-h-11 items-center gap-2 px-4">{inner}</div>
        )
      })}
    </Card>
  )
}

/** 일정 없이 전술만 볼 때 */
function PlainBoard({ play, note }: { play: Play; note: string | null }) {
  return (
    <Screen>
      <TopBar title="전술판" back="/" />
      <Content>
        <PlayHeader play={play} />
        {note && <Alert kind="info">{note}</Alert>}
        <TacticBoard key={play.key} play={play} />
        <RoleList play={play} />
      </Content>
    </Screen>
  )
}

/** 그날 이름표와 함께 */
function EventBoard({ play, view, eventId }: { play: Play; view: EventPlayView; eventId: number }) {
  const [sp] = useSearchParams()
  const qc = useQueryClient()
  const squads = view.squads
  const fill = sp.get('fill')?.split(',').map(Number).filter(Boolean) ?? []
  const fillSquad = Number(sp.get('squad')) || null
  const [squadNo, setSquadNo] = useState<number>(() => fillSquad ?? view.my_squad_no ?? squads[0].squad_no)
  const saved = useMemo(() => draftFrom(view), [view])
  const [draft, setDraft] = useState<Draft>(() => {
    const d = draftFrom(view)
    if (view.can_edit && fillSquad && fill.length === 5 && d[fillSquad]) d[fillSquad] = fill
    return d
  })
  const [picking, setPicking] = useState<number | null>(null)
  const [done, setDone] = useState(false)
  const sq = squads.find((s) => s.squad_no === squadNo) ?? squads[0]
  const row = draft[sq.squad_no] ?? [null, null, null, null, null]
  const nameOf = (pid: number | null) => (pid === null ? null : sq.members.find((m) => m.player_id === pid)?.display_name ?? null)
  const names = row.map(nameOf)
  const dirty = JSON.stringify(row) !== JSON.stringify(saved[sq.squad_no] ?? [null, null, null, null, null])
  const fromRecommend = view.can_edit && fillSquad === sq.squad_no && dirty

  const save = useMutation({
    mutationFn: () => tacticsApi.saveSlots(eventId, view.play_key, {
      squad_no: sq.squad_no,
      slots: row.flatMap((pid, i) => (pid === null ? [] : [{ slot: i + 1, player_id: pid }])),
    }),
    onSuccess: (v) => {
      qc.setQueryData(['tactics', 'event', eventId, view.play_key], v)
      qc.invalidateQueries({ queryKey: ['tactics', 'saved', eventId] })
      setDone(true)
    },
  })

  const assign = (slot: number, pid: number | null) => {
    const next = [...row]
    if (pid !== null) {
      const already = next.indexOf(pid)
      if (already >= 0) next[already] = next[slot - 1] // 다른 자리에 있던 사람이면 서로 바꾼다
    }
    next[slot - 1] = pid
    setDraft({ ...draft, [sq.squad_no]: next })
    setPicking(null)
    setDone(false)
  }

  return (
    <Screen>
      <TopBar title="전술판" back="/" />
      <Content>
        <PlayHeader play={play} />
        {squads.length > 1 && (
          <div className="grid grid-cols-2 gap-1 rounded-xl bg-sunken p-1" role="tablist" aria-label="팀 고르기">
            {squads.map((s) => (
              <button
                key={s.squad_no} type="button" role="tab" aria-selected={s.squad_no === sq.squad_no}
                onClick={() => { setSquadNo(s.squad_no); setDone(false) }}
                className={`min-h-10 rounded-lg text-sm font-semibold ${s.squad_no === sq.squad_no ? (s.squad_no === 1 ? 'bg-team-black text-team-black-ink' : 'border border-line-strong bg-team-white text-team-white-ink') : 'text-muted'}`}
              >
                {s.squad_name}{view.my_squad_no === s.squad_no ? ' · 내 팀' : ''}
              </button>
            ))}
          </div>
        )}
        {fromRecommend && <Alert kind="info">추천 배치를 채워 뒀어요. 저장하면 그날 참석자에게 보여요.</Alert>}
        {done && !dirty && <Alert kind="info">저장했어요. 그날 참석자가 전술 탭에서 볼 수 있어요.</Alert>}
        {save.isError && <Alert>{errMsg(save.error, '저장하지 못했어요.')}</Alert>}
        <TacticBoard key={play.key} play={play} tone={toneOf(sq.squad_no)} names={names} onSlotTap={view.can_edit ? setPicking : undefined} />
        <RoleList play={play} names={names} onTap={view.can_edit ? setPicking : undefined} />
        {!view.can_edit && names.every((n) => n === null) && <p className="text-center text-xs text-muted">매니저가 아직 이 팀 이름표를 정하지 않았어요.</p>}
      </Content>
      {view.can_edit && (
        <BottomAction>
          <Button full disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>{sq.squad_name} 이름표 저장</Button>
        </BottomAction>
      )}
      {picking !== null && (
        <PickSheet squad={sq} slot={picking} role={ROLE_LABEL[play.roles[picking - 1]]} row={row} onPick={(pid) => assign(picking, pid)} onClose={() => setPicking(null)} />
      )}
    </Screen>
  )
}

function PickSheet({ squad, slot, role, row, onPick, onClose }: {
  squad: SquadTags; slot: number; role: string; row: (number | null)[]; onPick: (pid: number | null) => void; onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40" onClick={onClose} role="dialog" aria-modal="true" aria-label={`${slot}번 자리 선수 고르기`}>
      <div className="safe-bottom max-h-[80vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-strong" />
        <div className="flex items-start justify-between">
          <h3 className="text-lg font-bold text-ink">{CIRCLED[slot - 1]} {role}</h3>
          <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 flex size-9 items-center justify-center rounded-full text-xl text-faint active:bg-sunken">×</button>
        </div>
        <p className="mb-3 text-xs text-muted">{squad.squad_name} 팀에서 이 자리에 설 사람을 골라요. 다른 자리에 있던 사람을 고르면 두 자리가 바뀌어요.</p>
        <div className="space-y-1.5">
          {squad.members.map((m) => {
            const at = row.indexOf(m.player_id)
            const here = at === slot - 1
            return (
              <button
                key={m.player_id} type="button" onClick={() => onPick(m.player_id)}
                className={`flex min-h-11 w-full items-center justify-between rounded-xl border px-4 text-left text-sm ${here ? 'border-court-500 bg-brand-soft font-semibold text-brand-ink' : 'border-line bg-surface text-ink active:bg-sunken'}`}
              >
                <span>{m.display_name}{m.is_guest ? <span className="ml-1 text-xs text-muted">게스트</span> : null}</span>
                {at >= 0 && !here && <span className="text-xs text-muted">지금 {CIRCLED[at]}</span>}
              </button>
            )
          })}
        </div>
        {row[slot - 1] !== null && (
          <Button variant="ghost" full className="mt-3" onClick={() => onPick(null)}>이 자리 비우기</Button>
        )}
      </div>
    </div>
  )
}
