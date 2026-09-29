/**
 * S-29 전술판 (docs/07 FR-47). 경로: /tactics/:key?event=일정&squad=팀번호
 *
 * - `event` 가 없으면 전술 설명만 (전술 탭 목록에서 들어왔고 그날 참석자가 아닌 경우).
 * - `event` 가 있으면 그날 블랙/화이트의 자리 배치를 함께 보여 준다. 배치는 서버가 자동으로 추천한 것이고,
 *   매니저가 자리를 바꿔 저장했으면 그 배치다. 자리 목록에는 괄호로 예비(같은 전술판 5명 중 그 역할도 맞는 사람)를 단다.
 * - 매니저는 동그라미나 자리 목록을 눌러 사람을 바꾸고 저장한다. "추천 배치로 되돌리기" 로 저장을 지운다.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { tacticsApi } from '../api/tactics'
import type { EventPlayView, Play, SlotLineup, SquadBoard } from '../api/types'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { TacticBoard, type BoardTone } from '../components/tactic-board'
import { CIRCLED, SlotPeople } from '../components/tactics'
import { Alert, Badge, Button, Card, Spinner } from '../components/ui'
import { DEFENSE_LABEL, ROLE_LABEL, renderCounter } from '../lib/tactics'

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)
const toneOf = (squadNo: number): BoardTone => (squadNo === 1 ? 'black' : 'white')

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

  // 일정 배치를 불러오는 동안 일정 없는 전술판을 먼저 그리면, 다 불러온 뒤 전술판이 새로 그려지며 그 사이 누른 재생·다음이 사라진다
  if (!play || (eventId !== null && view.isLoading)) {
    return (
      <Screen>
        <TopBar title="전술" back="/" />
        {presets.isLoading || view.isLoading ? <Spinner /> : <Content><Alert>없는 전술이에요.</Alert></Content>}
      </Screen>
    )
  }
  const withEvent = view.data && view.data.squads.length > 0 ? view.data : null
  return withEvent ? <EventBoard play={play} view={withEvent} eventId={eventId!} /> : <PlainBoard play={play} note={view.isError ? errMsg(view.error, '') : null} />
}

function PlayHeader({ play }: { play: Play }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-bold text-ink">{play.name}</h2>
        {play.situation === 'inbound'
          ? <Badge tone="court">인바운드</Badge>
          : <Badge tone={play.defense === 'zone' ? 'navy' : 'neutral'}>{DEFENSE_LABEL[play.defense]}</Badge>}
      </div>
      <p className="text-sm text-muted">{play.summary}</p>
    </div>
  )
}

function RoleList({ play, slots, onTap }: { play: Play; slots?: SlotLineup[]; onTap?: (slot: number) => void }) {
  return (
    <Card className="divide-y divide-line p-0">
      {play.roles.map((role, i) => {
        const s = slots?.[i]
        const inner = (
          <>
            <span className="w-6 shrink-0 text-base font-bold text-brand-ink">{CIRCLED[i]}</span>
            <span className="w-24 shrink-0 text-sm text-ink-2">{ROLE_LABEL[role]}</span>
            <span className="min-w-0 flex-1 text-sm">{s ? <SlotPeople s={s} /> : null}</span>
            {onTap && <span className="text-faint" aria-hidden="true">›</span>}
          </>
        )
        return onTap ? (
          <button key={i} type="button" onClick={() => onTap(i + 1)} className="flex min-h-11 w-full items-center gap-2 px-4 py-2 text-left active:bg-sunken">{inner}</button>
        ) : (
          <div key={i} className="flex min-h-11 items-center gap-2 px-4 py-2">{inner}</div>
        )
      })}
    </Card>
  )
}

/** 막혔을 때의 대안 */
function Counter({ text }: { text: string }) {
  if (!text) return null
  return <p className="rounded-xl bg-sunken px-3 py-2.5 text-sm leading-relaxed text-ink-2"><b className="text-ink">막히면</b> · {text}</p>
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
        <Counter text={renderCounter(play.counter)} />
      </Content>
    </Screen>
  )
}

/** 그날 자리 배치와 함께 */
function EventBoard({ play, view, eventId }: { play: Play; view: EventPlayView; eventId: number }) {
  const [sp] = useSearchParams()
  const qc = useQueryClient()
  const squads = view.squads
  const [squadNo, setSquadNo] = useState<number>(() => Number(sp.get('squad')) || view.my_squad_no || squads[0].squad_no)
  const [draft, setDraft] = useState<Partial<Record<number, number[]>>>({}) // 매니저가 바꾸는 중인 배치 (squad_no → 슬롯 순 player_id)
  const [picking, setPicking] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const sq = squads.find((s) => s.squad_no === squadNo) ?? squads[0]
  const lineup = sq.lineup
  const savedRow = lineup?.slots.map((s) => s.player_id) ?? []
  const row = draft[sq.squad_no] ?? savedRow
  const dirty = row.join() !== savedRow.join()
  const nameOf = (pid: number) => sq.members.find((m) => m.player_id === pid)?.display_name ?? null
  // 바꾸는 중이면 예비는 저장 뒤에 다시 계산되므로 이름만 보여 준다
  const slots: SlotLineup[] | undefined = lineup?.slots.map((s, i) => (
    dirty ? { ...s, player_id: row[i], display_name: nameOf(row[i]) ?? '', backups: [] } : s
  ))

  const save = useMutation({
    mutationFn: (slotsIn: { slot: number; player_id: number }[]) => tacticsApi.saveSlots(eventId, view.play_key, { squad_no: sq.squad_no, slots: slotsIn }),
    onSuccess: (v, slotsIn) => {
      qc.setQueryData(['tactics', 'event', eventId, view.play_key], v)
      qc.invalidateQueries({ queryKey: ['tactics', 'recommend', eventId] })
      setDraft({ ...draft, [sq.squad_no]: undefined })
      setNotice(slotsIn.length ? '저장했어요. 그날 참석자에게 이 배치로 보여요.' : '추천 배치로 되돌렸어요.')
    },
  })

  const assign = (slot: number, pid: number) => {
    const next = [...row]
    const already = next.indexOf(pid)
    if (already >= 0) next[already] = next[slot - 1] // 다른 자리에 있던 사람이면 서로 바꾼다
    next[slot - 1] = pid
    setDraft({ ...draft, [sq.squad_no]: next })
    setPicking(null)
    setNotice(null)
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
                onClick={() => { setSquadNo(s.squad_no); setNotice(null) }}
                className={`min-h-10 rounded-lg text-sm font-semibold ${s.squad_no === sq.squad_no ? (s.squad_no === 1 ? 'bg-team-black text-team-black-ink' : 'border border-line-strong bg-team-white text-team-white-ink') : 'text-muted'}`}
              >
                {s.squad_name}{view.my_squad_no === s.squad_no ? ' · 내 팀' : ''}
              </button>
            ))}
          </div>
        )}
        {!lineup ? (
          <Alert kind="info">이 팀은 5명이 안 돼서 자리를 정할 수 없어요.</Alert>
        ) : (
          <>
            <div className="flex items-center gap-2 text-xs text-muted">
              <span>적합도 <b className="text-brand-ink">{Math.round(lineup.fit)}</b></span>
              <span>·</span>
              <span>{lineup.manual ? '매니저가 정한 배치' : '자동 추천 배치'}</span>
            </div>
            {notice && <Alert kind="info">{notice}</Alert>}
            {save.isError && <Alert>{errMsg(save.error, '저장하지 못했어요.')}</Alert>}
            <TacticBoard key={play.key} play={play} tone={toneOf(sq.squad_no)} names={row.map(nameOf)} onSlotTap={view.can_edit ? setPicking : undefined} />
            <RoleList play={play} slots={slots} onTap={view.can_edit ? setPicking : undefined} />
            <Counter text={renderCounter(play.counter, row.map(nameOf))} />
            <p className="text-[11px] text-faint">괄호 안은 같은 전술판 5명 중에서 그 역할도 할 수 있는 예비예요.</p>
          </>
        )}
      </Content>
      {view.can_edit && lineup && (dirty || lineup.manual) && (
        <BottomAction>
          <div className="flex gap-2">
            {lineup.manual && !dirty && (
              <Button full variant="ghost" loading={save.isPending} onClick={() => save.mutate([])}>추천 배치로 되돌리기</Button>
            )}
            {dirty && (
              <>
                <Button variant="ghost" className="shrink-0 whitespace-nowrap" onClick={() => setDraft({ ...draft, [sq.squad_no]: undefined })}>취소</Button>
                <Button full loading={save.isPending} onClick={() => save.mutate(row.map((pid, i) => ({ slot: i + 1, player_id: pid })))}>{sq.squad_name} 배치 저장</Button>
              </>
            )}
          </div>
        </BottomAction>
      )}
      {picking !== null && (
        <PickSheet squad={sq} slot={picking} role={ROLE_LABEL[play.roles[picking - 1]]} row={row} onPick={(pid) => assign(picking, pid)} onClose={() => setPicking(null)} />
      )}
    </Screen>
  )
}

function PickSheet({ squad, slot, role, row, onPick, onClose }: {
  squad: SquadBoard; slot: number; role: string; row: number[]; onPick: (pid: number) => void; onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40" onClick={onClose} role="dialog" aria-modal="true" aria-label={`${slot}번 자리 선수 고르기`}>
      <div className="safe-bottom max-h-[80vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-strong" />
        <div className="flex items-start justify-between">
          <h3 className="text-lg font-bold text-ink">{CIRCLED[slot - 1]} {role}</h3>
          <button type="button" onClick={onClose} aria-label="닫기" className="-mr-1 -mt-1 flex size-9 items-center justify-center rounded-full text-xl text-faint active:bg-sunken">×</button>
        </div>
        <p className="mb-3 text-xs text-muted">{squad.squad_name} 팀에서 이 자리에 설 사람을 골라요. 다른 자리에 있던 사람을 고르면 두 자리가 바뀌고, 벤치에 있던 사람을 고르면 지금 사람이 벤치로 가요.</p>
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
                <span className="text-xs text-muted">{at >= 0 ? (here ? '지금 이 자리' : `지금 ${CIRCLED[at]}`) : '벤치'}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
