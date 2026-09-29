/**
 * S-29 전술판 (docs/07 FR-47). 경로: /tactics/:key?event=일정&squad=팀번호&team=팀
 *
 * - `key` 는 프리셋 키("high_pnr") 또는 팀이 만든 전술("team_12", docs/07 FR-57). 팀 전술은 `team`(또는 일정의 팀)이 있어야 연다.
 * - 아래에 팀 안의 전술 댓글(FR-60). 팀 전술이면 만든 사람과 매니저에게 "고치기".
 * - 수비는 전술이 가정한 방식(opp_defense · screen_call)으로 고정이다 — 고르는 칸이 없다 (v1.7).
 * - `event` 가 없으면 전술 설명만 (전술 탭 목록에서 들어왔고 그날 참석자가 아닌 경우).
 * - `event` 가 있으면 그날 그 팀(`squad`, 없으면 내 팀)의 자리 배치를 함께 보여 준다. 상대 팀으로 바꿔 보는 칸은 없다. 배치는 서버가 자동으로 추천한 것이고,
 *   매니저가 자리를 바꿔 저장했으면 그 배치다. 자리 목록에는 괄호로 예비(같은 전술판 5명 중 그 역할도 맞는 사람)를 단다.
 * - 매니저는 동그라미나 자리 목록을 눌러 사람을 바꾸고 저장한다. "추천 배치로 되돌리기" 로 저장을 지운다.
 */
import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { tacticsApi, teamPlaysApi } from '../api/tactics'
import type { EventPlayView, Play, SlotLineup, SquadBoard } from '../api/types'
import { BottomAction, Content, Screen, TopBar } from '../components/layout'
import { TacticBoard, type BoardTone } from '../components/tactic-board'
import { TacticComments } from '../components/tactic-comments'
import { CIRCLED, SlotPeople, TacticExplain, useAiTactics } from '../components/tactics'
import { Alert, Badge, Button, SectionTitle, Spinner } from '../components/ui'
import { DEFENSE_LABEL, ROLE_LABEL, renderCounter } from '../lib/tactics'
import { squadStyle, squadTone } from '../lib/squads'

const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)
const toneOf = (squadNo: number): BoardTone => squadTone(squadNo)

export function TacticBoardPage() {
  const { key = '' } = useParams()
  const [sp] = useSearchParams()
  const eventId = Number(sp.get('event')) || null
  const teamPlayId = key.startsWith('team_') ? Number(key.slice(5)) || null : null
  const playKey = teamPlayId ? `team:${teamPlayId}` : `preset:${key}`
  const presets = useQuery({ queryKey: ['tactics', 'presets'], queryFn: tacticsApi.presets, staleTime: Infinity, enabled: !teamPlayId })
  const view = useQuery({
    queryKey: ['tactics', 'event', eventId, playKey], queryFn: () => tacticsApi.play(eventId!, playKey), enabled: eventId !== null,
    retry: false,
  })
  const teamId = view.data?.team_id ?? (Number(sp.get('team')) || null)
  const own = useQuery({
    queryKey: ['tactics', 'team-play', teamId, teamPlayId], queryFn: () => teamPlaysApi.get(teamId!, teamPlayId!),
    enabled: teamPlayId !== null && teamId !== null, retry: false,
  })
  const play: Play | undefined = view.data?.play ?? (teamPlayId ? own.data?.play : presets.data?.items.find((p) => p.key === key))
  const loading = presets.isLoading || view.isLoading || own.isLoading

  // 일정 배치를 불러오는 동안 일정 없는 전술판을 먼저 그리면, 다 불러온 뒤 전술판이 새로 그려지며 그 사이 누른 재생·다음이 사라진다
  if (!play || (eventId !== null && view.isLoading)) {
    return (
      <Screen>
        <TopBar title="전술" back="/" />
        {loading ? <Spinner /> : <Content><Alert>없는 전술이에요.</Alert></Content>}
      </Screen>
    )
  }
  // 팀 전술 고치기는 만든 사람과 매니저 (v1.7)
  const editPath = teamPlayId && teamId && own.data?.can_edit ? `/teams/${teamId}/plays/${teamPlayId}/edit` : null
  const withEvent = view.data && view.data.squads.length > 0 ? view.data : null
  return withEvent
    ? <EventBoard play={play} view={withEvent} eventId={eventId!} editPath={editPath} />
    : <PlainBoard play={play} note={view.isError ? errMsg(view.error, '') : null} teamId={teamId} playKey={playKey} editPath={editPath} />
}

function EditLink({ to }: { to: string | null }) {
  return to ? <Link to={to} className="mr-1 text-sm font-semibold text-brand-ink">고치기</Link> : null
}

function PlayHeader({ play, context }: { play: Play; context?: ReactNode }) {
  return (
    <div className="space-y-1.5 px-1">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-black text-ink">{play.name}</h2>
        {play.situation === 'inbound'
          ? <Badge tone="court">인바운드</Badge>
          : <Badge tone={play.defense === 'zone' ? 'navy' : 'neutral'}>{DEFENSE_LABEL[play.defense]}</Badge>}
      </div>
      {context}
    </div>
  )
}

function RoleList({ play, slots, onTap }: { play: Play; slots?: SlotLineup[]; onTap?: (slot: number) => void }) {
  return (
    <section>
      <SectionTitle>자리</SectionTitle>
      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {play.roles.map((role, i) => {
          const s = slots?.[i]
          const inner = (
            <>
              <span className="w-5 shrink-0 text-center text-sm font-bold text-brand-ink">{CIRCLED[i]}</span>
              <span className="w-[5.5rem] shrink-0 text-sm text-ink-2">{ROLE_LABEL[role]}</span>
              <span className="min-w-0 flex-1 text-sm">{s ? <SlotPeople s={s} /> : null}</span>
              {onTap && <span className="text-xs font-semibold text-brand-ink">바꾸기</span>}
            </>
          )
          return (
            <li key={i}>
              {onTap ? (
                <button type="button" onClick={() => onTap(i + 1)} className="flex min-h-12 w-full items-center gap-3 px-4 py-2 text-left active:bg-sunken">{inner}</button>
              ) : (
                <div className="flex min-h-12 items-center gap-3 px-4 py-2">{inner}</div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** 일정 없이 전술만 볼 때 — 자리는 번호로 */
function PlainBoard({ play, note, teamId, playKey, editPath }: { play: Play; note: string | null; teamId: number | null; playKey: string; editPath: string | null }) {
  return (
    <Screen>
      <TopBar title="전술판" back="/" right={<EditLink to={editPath} />} />
      <Content>
        <PlayHeader play={play} />
        <TacticExplain summary={play.summary} counter={renderCounter(play.counter)} />
        {note && <Alert kind="info">{note}</Alert>}
        <TacticBoard key={play.key} play={play} />
        <RoleList play={play} />
        {teamId && <TacticComments teamId={teamId} playKey={playKey} />}
      </Content>
    </Screen>
  )
}

/**
 * 추천 전술에서 들어온 전술판 — 그 팀 전용. 상대 팀으로 바꿔 보는 칸은 없다 (팀원은 내 팀, 매니저는 들어온 팀).
 * 전술 소개 바로 아래에 추천 카드와 같은 "전술 설명"(AI 이유 · 핵심 자리 · 주의할 점 · 막히면)을 둔다.
 */
function EventBoard({ play, view, eventId, editPath }: { play: Play; view: EventPlayView; eventId: number; editPath: string | null }) {
  const [sp] = useSearchParams()
  const qc = useQueryClient()
  const zone = sp.get('zone') === '1'
  const wanted = Number(sp.get('squad')) || view.my_squad_no
  const sq = view.squads.find((s) => s.squad_no === wanted) ?? view.squads[0]
  const ai = useAiTactics(eventId, sq.squad_no, zone, true)
  const aiItem = ai.data && !ai.data.fallback ? ai.data.items.find((x) => x.play_key === view.play_key) : undefined
  const [draft, setDraft] = useState<number[] | null>(null) // 매니저가 바꾸는 중인 배치 (슬롯 순 player_id)
  const [picking, setPicking] = useState<number | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const lineup = sq.lineup
  const savedRow = lineup?.slots.map((s) => s.player_id) ?? []
  const row = draft ?? savedRow
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
      setDraft(null)
      setNotice(slotsIn.length ? '저장했어요. 그날 참석자에게 이 배치로 보여요.' : '추천 배치로 되돌렸어요.')
    },
  })

  const assign = (slot: number, pid: number) => {
    const next = [...row]
    const already = next.indexOf(pid)
    if (already >= 0) next[already] = next[slot - 1] // 다른 자리에 있던 사람이면 서로 바꾼다
    next[slot - 1] = pid
    setDraft(next)
    setPicking(null)
    setNotice(null)
  }

  const context = lineup && (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
      <span className="inline-flex items-center gap-1.5 font-semibold text-ink-2">
        <span className={`size-2.5 rounded-full ${squadStyle(sq.squad_no).dot}`} aria-hidden="true" />
        {sq.squad_name}{view.my_squad_no === sq.squad_no ? ' · 내 팀' : ''}
      </span>
      <span>적합도 <b className="text-brand-ink">{Math.round(lineup.fit)}</b></span>
      <span>{lineup.manual ? '매니저가 정한 배치' : '자동 추천 배치'}</span>
    </p>
  )

  return (
    <Screen>
      <TopBar title="전술판" back="/" right={<EditLink to={editPath} />} />
      <Content>
        <PlayHeader play={play} context={context} />
        {!lineup ? (
          <Alert kind="info">이 팀은 5명이 안 돼서 자리를 정할 수 없어요.</Alert>
        ) : (
          <>
            <TacticExplain summary={play.summary} ai={aiItem} counter={renderCounter(play.counter, row.map(nameOf))} />
            {notice && <Alert kind="info">{notice}</Alert>}
            {save.isError && <Alert>{errMsg(save.error, '저장하지 못했어요.')}</Alert>}
            <TacticBoard key={play.key} play={play} tone={toneOf(sq.squad_no)} names={row.map(nameOf)} onSlotTap={view.can_edit ? setPicking : undefined} />
            <RoleList play={play} slots={slots} onTap={view.can_edit ? setPicking : undefined} />
          </>
        )}
        <TacticComments teamId={view.team_id} playKey={view.play_key} />
      </Content>
      {view.can_edit && lineup && (dirty || lineup.manual) && (
        <BottomAction>
          <div className="flex gap-2">
            {lineup.manual && !dirty && (
              <Button full variant="ghost" loading={save.isPending} onClick={() => save.mutate([])}>추천 배치로 되돌리기</Button>
            )}
            {dirty && (
              <>
                <Button variant="ghost" className="shrink-0 whitespace-nowrap" onClick={() => setDraft(null)}>취소</Button>
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
