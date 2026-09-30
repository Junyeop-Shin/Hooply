/**
 * 확정된 팀 배정 표시 (S-14) — 일정 화면의 "팀 배정 결과", 팀 일정 탭의 확정 요약, 배정 결과 화면의 팀 카드.
 * 일정 · 팀 화면이 배정 실행 페이지(pages/assignment) 전체를 끌어오지 않도록 따로 둔다.
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { assignmentsApi } from '../api/assignments'
import { teamsApi } from '../api/teams'
import type { EventView, PlayerCard, SquadView } from '../api/types'
import { SHARE_DONE, shareImage } from '../lib/kakao'
import { fmtEvent } from '../lib/format'
import { squadStyle } from '../lib/squads'
import { AiExplainCard, AiMessageCard } from './ai-cards'
import { FirstTimeTip } from './tutorial'
import { Badge, Card, GradeDot, SectionTitle, Spinner } from './ui'

/** 명단이 바뀌면 달라지는 값 — AI 설명을 새로 부를지 가르는 데 쓴다 */
export const rosterKey = (squads: SquadView[]) => squads.map((sq) => sq.members.map((m) => m.id).sort((a, b) => a - b).join('.')).join('|')

export type Marks = { locked: Map<number, number>; lockGroups: Map<number, number[]>; pinned: Set<number>; sepGroup: Map<number, number[]> }

/** 팀 카드. narrow = 3팀을 한 줄에 셋 놓을 때 — 글자를 줄이고 표시를 한 글자로 */
export function SquadCard({ squad, picked, onPick, showSkill, highlightId, marks, title, compact, narrow }: { squad: SquadView; picked?: number[]; onPick?: (pid: number) => void; showSkill?: boolean; highlightId?: number; marks?: Marks; title?: string; compact?: boolean; narrow?: boolean }) {
  const st = squadStyle(squad.squad_no)
  const dark = squad.squad_no !== 2
  const tag = (full: string, short: string) => (narrow ? short : full)
  return (
    <div className={`min-w-0 rounded-2xl border-2 ${narrow ? 'p-2' : 'p-3'} ${st.card}`}>
      <div className={`flex flex-wrap items-center justify-between gap-1 font-bold ${narrow ? 'text-xs' : 'text-sm'}`}>
        <span>{title ?? squad.squad_name} ({squad.members.length})</span>
        {!compact && showSkill && squad.avg_skill !== null && <Badge tone={dark ? 'court' : 'navy'}>{narrow ? '' : '쿼터당 '}{Number(squad.avg_skill) > 0 ? '+' : ''}{squad.avg_skill}</Badge>}
      </div>
      {!compact && squad.avg_height_cm !== null && <p className={`text-[11px] ${st.sub}`}>{narrow ? '' : '평균 신장 '}{squad.avg_height_cm}cm</p>}
      <ul className="mt-2 space-y-1">
        {squad.members.map((m) => {
          const pos = squad.assigned_positions[m.id]
          const on = picked?.includes(m.id) ?? false
          const me = highlightId === m.id
          const Row = onPick ? 'button' : 'div'  // 고를 수 없는 결과 화면에서는 누를 수 없는 줄 (쓸데없는 탭 이동을 만들지 않게)
          return (
            <li key={m.id}>
              <Row
                {...(onPick && { type: 'button' as const, onClick: () => onPick(m.id), 'aria-pressed': on })}
                className={`flex w-full items-center gap-1 rounded-lg ${narrow ? 'px-1 py-0.5 text-xs' : 'gap-1.5 px-1.5 py-1 text-sm'} text-left ${on ? st.picked : me ? st.soft : ''}`}
              >
                <span className={`${narrow ? 'w-4 text-[9px]' : 'w-6 text-[10px]'} shrink-0 font-bold ${st.sub}`}>{pos ?? '—'}</span>
                <span className="min-w-0 truncate font-medium">{m.display_name}{me ? ' (나)' : ''}</span>
                {m.kind === 'GUEST' && <span className={`shrink-0 text-[10px] ${st.sub}`}>G</span>}
                {squad.manual_override_ids.includes(m.id) && <span className="text-[10px] text-amber-400">↔</span>}
                {marks?.locked.has(m.id) && <span className={`shrink-0 rounded px-1 text-[9px] font-semibold ${dark ? `bg-white/15 ${st.sub}` : 'bg-navy-100 text-navy-700'}`} title="같은 팀으로 묶음">{tag('묶음', '묶')}{marks.locked.get(m.id)}</span>}
                {marks?.pinned.has(m.id) && <span className={`shrink-0 rounded px-1 text-[9px] font-semibold ${dark ? `bg-white/15 ${st.sub}` : 'bg-navy-100 text-navy-700'}`} title="사전 배치">{tag('고정', '고')}</span>}
                {marks?.sepGroup.has(m.id) && <span className={`shrink-0 rounded px-1 text-[9px] font-semibold ${dark ? `bg-white/15 ${st.sub}` : 'bg-rose-100 text-rose-700'}`} title="갈라놓기">{tag('분리', '분')}</span>}
                {showSkill && <span className="ml-auto shrink-0"><GradeDot grade={m.skill_grade} small={narrow} /></span>}
              </Row>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/**
 * 일정 화면의 팀 배정 결과 (S-14, 배정이 확정된 일정). 순서: 내 팀 → 배정 설명(AI) → 두 팀 명단.
 * 카카오톡 공유는 매니저만 — 팀원은 결과만 보면 된다. 추천 전술은 일정 화면이 이 아래에 붙인다.
 */
export function AdoptedSection({ event: e }: { event: EventView }) {
  const id = e.id
  const view = useQuery({ queryKey: ['events', id, 'adopted'], queryFn: () => assignmentsApi.adopted(id), retry: false })
  const isManager = e.my_role === 'MANAGER'
  const team = useQuery({ queryKey: ['team', e.team_id], queryFn: () => teamsApi.get(e.team_id), enabled: isManager })
  const [shareMsg, setShareMsg] = useState<string | null>(null)
  // 구성표 이미지 → 카카오톡. 실력 정보는 이미지에 넣지 않는다
  const share = useMutation({
    mutationFn: async () => {
      const v = view.data!
      const eventLine = `${fmtEvent(e)}${e.venue ? ` · ${e.venue}` : ''}`
      const { renderSquadImage } = await import('../lib/squad-image')  // 공유를 누를 때만 캔버스 코드를 불러온다
      const img = await renderSquadImage({ teamName: team.data?.name ?? '팀 배정', eventLine, squads: v.squads }, `팀배정-${e.event_date}.png`)
      return shareImage(img.file, { title: `${team.data?.name ?? '팀 배정'} · ${fmtEvent(e)}`, description: `팀 배정 결과예요. ${v.squads.map((s) => `${s.squad_name} ${s.members.length}명`).join(' · ')}`, url: `${location.origin}/events/${id}`, width: img.width, height: img.height })
    },
    onSuccess: (r) => setShareMsg(SHARE_DONE[r]),
    onError: (err) => setShareMsg(err instanceof Error ? err.message : '공유하지 못했어요.'),
  })
  if (view.isLoading) return <Spinner />
  if (!view.data) return null
  const v = view.data
  const mine = v.squads.find((s) => s.squad_no === v.my_squad_no)
  const others = v.squads.filter((s) => s.squad_no !== v.my_squad_no)
  const me: PlayerCard | undefined = mine?.members.find((m) => m.id === (v.my_player_id ?? undefined))

  return (
    <section className="space-y-3">
      <SectionTitle>팀 배정 결과</SectionTitle>
      <FirstTimeTip id="adopted" />
      {mine && (
        <div className={`flex items-center gap-3 rounded-2xl border px-4 py-3 ${squadStyle(mine.squad_no).card}`}>
          <span className="text-xs opacity-70">내 팀</span>
          <span className="text-xl font-black">{mine.squad_name}</span>
          {v.my_assigned_position && <span className="rounded-lg bg-court-500 px-2 py-0.5 text-sm font-bold text-white">{v.my_assigned_position}</span>}
        </div>
      )}
      {isManager
        ? <AiExplainCard candidateId={v.candidate_id} rosterKey={rosterKey(v.squads)} fallbackText={v.explanation} />
        : v.my_squad_no !== null ? <AiMessageCard eventId={id} fallbackText={v.explanation} /> : <Card><p className="whitespace-pre-line text-sm text-ink-2">{v.explanation}</p></Card>}
      {isManager && (
        <Card className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-ink">단체방에 팀 구성 보내기</p>
            <p className="text-xs text-muted">{shareMsg ?? `${v.squads.length === 3 ? '세' : '두'} 팀 명단을 이미지 한 장으로 보내요.`}</p>
          </div>
          <button
            onClick={() => share.mutate()} disabled={share.isPending}
            className="min-h-10 shrink-0 rounded-xl bg-[#FEE500] px-3 text-sm font-semibold text-[#191919] disabled:opacity-50"
          >
            {share.isPending ? '만드는 중…' : '카카오톡 공유'}
          </button>
        </Card>
      )}
      {mine ? (
        <>
          <SquadCard squad={mine} showSkill={isManager} highlightId={me?.id} title={`내 팀 · 팀 ${mine.squad_name}`} />
          {others.map((s) => <SquadCard key={s.squad_no} squad={s} showSkill={isManager} title={`상대 · 팀 ${s.squad_name}`} />)}
        </>
      ) : (
        <div className={`grid gap-2 ${v.squads.length === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
          {v.squads.map((s) => <SquadCard key={s.squad_no} squad={s} showSkill={isManager} title={`팀 ${s.squad_name}`} narrow={v.squads.length === 3} />)}
        </div>
      )}
      {!isManager && <p className="px-1 text-center text-xs text-faint">실력 수치는 표시하지 않아요. 등급은 경기 기록이 저장될 때마다 갱신돼요.</p>}
    </section>
  )
}



/** 팀 상세 일정 탭에서 확정된 배정을 대시보드처럼 보여준다: 내 팀(왼쪽) / 상대 팀(오른쪽) / 균형 점수 */
export function AdoptedSummary({ eventId, isManager }: { eventId: number; isManager: boolean }) {
  const nav = useNavigate()
  const view = useQuery({ queryKey: ['events', eventId, 'adopted'], queryFn: () => assignmentsApi.adopted(eventId), retry: false })
  if (!view.data) return null
  const v = view.data
  const mine = v.squads.find((s) => s.squad_no === v.my_squad_no)
  const others = v.squads.filter((s) => s.squad_no !== v.my_squad_no)
  const ordered = mine ? [mine, ...others] : v.squads  // 좌측 우리 팀, 우측 상대 팀
  const myId = v.my_player_id ?? undefined
  return (
    <div className="-mt-1 space-y-2 rounded-b-2xl border border-t-0 border-line bg-surface-2 px-3 py-3">
      <div className="flex items-center justify-between px-1">
        <p className="text-sm font-bold text-ink">팀 배정 확정</p>
        <button onClick={() => nav(`/events/${eventId}`)} className="text-xs font-semibold text-brand-ink">자세히 →</button>
      </div>
      <div className={`grid gap-2 ${ordered.length === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
        {ordered.map((s) => (
          <SquadCard key={s.squad_no} squad={s} showSkill={isManager} highlightId={myId} title={`팀 ${s.squad_name}`} compact narrow={ordered.length === 3} />
        ))}
      </div>
      {v.total_score !== null && v.total_score !== undefined && (
        <div className="flex items-center justify-between rounded-lg bg-surface px-3 py-1.5 text-xs">
          <span className="text-muted">균형 점수</span>
          <span className="font-bold text-ink">{v.total_score} <span className="text-[10px] font-normal text-faint">낮을수록 균형이 좋아요</span></span>
        </div>
      )}
    </div>
  )
}
