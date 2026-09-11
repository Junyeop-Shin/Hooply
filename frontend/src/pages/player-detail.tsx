/**
 * 매니저용 선수 실력 지표 화면 (S-08 → 지표 보기) + S-17 기록 조각(MarginTrend · QuarterList 는 프로필에서도 재사용).
 * 설문 사전값 · 매니저 정렬 순위 · 코트 마진(잔차) 이력 · 피어 투표 지목 수를 한 화면에서 보여 "왜 이 등급인가"를 설명한다.
 * 실력 수치는 매니저/ADMIN 에게만 내려온다 (13.1절 Q3). 원시 마진은 실력이 아니라 결과다 (9.1절) — 그렇게 표기한다.
 */
import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { peerApi } from '../api/peer'
import type { MarginPoint, QuarterRecord } from '../api/types'
import { Alert, Avatar, Badge, Card, GradeDot, SectionTitle, Spinner } from '../components/ui'
import { Content, Screen, TopBar } from '../components/layout'

const SOURCE_LABEL: Record<string, string> = {
  SURVEY: '온보딩 설문', MANAGER_SORT: '매니저 실력 정렬', RESIDUAL: '쿼터 기록(잔차)', PEER_VOTE: '피어 투표',
  MANAGER_ADJUST: '매니저 보정', ADMIN_ADJUST: '관리자 보정', MERGE: '게스트 기록 병합',
}
const PRIOR_LABEL: Record<string, string> = { SURVEY: '설문 기반', MANAGER: '매니저 지정 등급', DEFAULT: '클럽 평균 (데이터 없음)' }
const AXIS_LABEL: Record<string, string> = { shooting: '슛', ball_handling: '볼핸들링', passing: '패스', defense: '수비', rebound_post: '골밑', stamina: '체력' }

export function PlayerDetailPage() {
  const { teamId, playerId } = useParams()
  const pid = Number(playerId)
  const q = useQuery({ queryKey: ['stats', pid], queryFn: () => peerApi.stats(pid), retry: false })
  if (q.isLoading) return <Screen><TopBar title="실력 지표" back={`/teams/${teamId}/members`} /><Spinner /></Screen>
  if (!q.data) return <Screen><TopBar title="실력 지표" back={`/teams/${teamId}/members`} /><Content><Alert>불러오지 못했어요. 매니저만 볼 수 있어요.</Alert></Content></Screen>
  const s = q.data
  const p = s.player
  const num = (v: string | null | undefined, digits = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(digits))
  const signed = (v: string | null | undefined) => (v === null || v === undefined ? '—' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(1)}`)
  const conf = s.skill_confidence === null ? 0 : Number(s.skill_confidence)
  const wins = s.margin_trend.reduce((a, m) => a + m.wins, 0)

  return (
    <Screen>
      <TopBar tone="navy" title="실력 지표" back={`/teams/${teamId}/members`} />
      <div className="bg-navy-800 px-4 pb-4 text-white">
        <div className="flex items-center gap-3">
          <Avatar name={p.display_name} src={p.profile_image_url} size="lg" />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-bold">{p.display_name} {p.kind === 'GUEST' && <Badge>게스트</Badge>}</p>
            <p className="text-xs text-navy-200">{p.playable_positions.length ? p.playable_positions.join(' · ') : '포지션 미입력'} · 참석 {s.events_attended}회 · 출전 {s.quarters_played}쿼터</p>
          </div>
          <GradeDot grade={s.skill_grade} />
        </div>
      </div>
      <Content>
        {/* 종합 */}
        <Card>
          <div className="flex items-baseline justify-between">
            <p className="text-sm font-bold text-navy-900">종합 실력</p>
            <p className="text-2xl font-black text-navy-900">{signed(s.skill_overall ?? s.prior_overall)}<span className="ml-1 text-xs font-normal text-stone-400">점/쿼터</span></p>
          </div>
          <p className="mt-1 text-xs text-stone-500">이 선수가 코트에 있을 때 팀이 한 쿼터에 얻는 점수 기여의 추정치예요. 0이 클럽 평균.</p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-lg bg-stone-50 py-2"><p className="text-[10px] text-stone-500">사전값</p><p className="font-bold text-navy-900">{signed(s.prior_overall)}</p><p className="text-[10px] text-stone-400">{s.prior_source ? PRIOR_LABEL[s.prior_source] ?? s.prior_source : '—'}</p></div>
            <div className="rounded-lg bg-stone-50 py-2"><p className="text-[10px] text-stone-500">경기 반영 후</p><p className="font-bold text-navy-900">{signed(s.skill_overall)}</p><p className="text-[10px] text-stone-400">{s.skill_overall === null ? '아직 반영 전' : `잔차 누적 ${signed(s.cumulative_residual)}`}</p></div>
            <div className="rounded-lg bg-stone-50 py-2"><p className="text-[10px] text-stone-500">신뢰도</p><p className="font-bold text-navy-900">{Math.round(conf * 100)}%</p><p className="text-[10px] text-stone-400">{conf < 0.3 ? '데이터 부족' : conf < 0.6 ? '보통' : '높음'}</p></div>
          </div>
        </Card>

        {/* 근거 3가지 */}
        <section>
          <SectionTitle>어떻게 계산됐나</SectionTitle>
          <div className="space-y-2">
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-navy-900">설문 사전값</p>
                <p className="text-xs text-stone-500">{s.prior_source === 'SURVEY' ? '온보딩 설문(구력·슛 거리·볼 운반·수비 이해도) + 동호회 내 자기 위치를 팀 내 상대 점수로 환산' : s.prior_source === 'MANAGER' ? '등록자가 지정한 등급을 팀 내 분위수로 환산' : '설문 응답이 없어 클럽 평균으로 시작'}</p>
              </div>
              <span className="text-sm font-bold text-navy-900">{signed(s.prior_overall)}</span>
            </Card>
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-navy-900">매니저 실력 정렬</p>
                <p className="text-xs text-stone-500">{s.manager_rank ? `활성 정렬 ${s.manager_rank.total}명 중 ${s.manager_rank.rank_no}위 · 설문 0.5 + 정렬 0.5 로 사전값에 결합` : '아직 정렬에 포함되지 않았어요 (설문값만 사용)'}</p>
              </div>
              {s.manager_rank && <span className="text-sm font-bold text-navy-900">{s.manager_rank.rank_no}<span className="text-xs font-normal text-stone-400">/{s.manager_rank.total}</span></span>}
            </Card>
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-navy-900">코트 마진 잔차</p>
                <p className="text-xs text-stone-500">{s.quarters_played === 0 ? '출전 기록이 없어요' : `출전 ${s.quarters_played}쿼터 · 이긴 쿼터 ${wins}개 · 기대 마진 대비 초과분을 누적해 갱신 (첫 2회 모임은 미반영)`}</p>
              </div>
              <span className={`text-sm font-bold ${Number(s.cumulative_residual ?? 0) < 0 ? 'text-rose-600' : 'text-navy-900'}`}>{signed(s.cumulative_residual)}</span>
            </Card>
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-navy-900">피어 투표</p>
                <p className="text-xs text-stone-500">"다음에 같이 뛰고 싶은 사람"으로 지목 {s.play_again_received ?? 0}회 · 상호 지목 {s.play_again_mutual ?? 0}쌍. 실력 계산에는 넣지 않고 친화도 우선 배정에만 반영돼요.</p>
              </div>
            </Card>
          </div>
        </section>

        {Object.keys(s.skill_axes).length > 0 && (
          <section>
            <SectionTitle>세부 6축 (설문 기반)</SectionTitle>
            <Card className="grid grid-cols-3 gap-2 text-center">
              {Object.entries(s.skill_axes).map(([k, v]) => (
                <div key={k} className="rounded-lg bg-stone-50 py-2"><p className="text-[10px] text-stone-500">{AXIS_LABEL[k] ?? k}</p><p className="text-sm font-bold text-navy-900">{num(v)}</p></div>
              ))}
            </Card>
          </section>
        )}

        <section>
          <SectionTitle>회차별 코트 마진</SectionTitle>
          <MarginTrend points={s.margin_trend} />
        </section>
        <section>
          <SectionTitle>최근 쿼터</SectionTitle>
          <QuarterList records={s.recent_quarters} />
        </section>

        {s.history.length > 0 && (
          <section>
            <SectionTitle>실력값 변동 이력</SectionTitle>
            <Paged items={s.history} render={(h, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-xs">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-navy-900">{SOURCE_LABEL[h.source] ?? h.source}</p>
                    <p className="truncate text-stone-500">{h.reason ?? ''} · {new Date(h.created_at).toLocaleDateString('ko-KR')}</p>
                  </div>
                  <span className="text-stone-500">{signed(h.before_value)} → <b className={Number(h.delta ?? 0) < 0 ? 'text-rose-600' : 'text-navy-900'}>{signed(h.after_value)}</b></span>
                </div>
              )} />
          </section>
        )}
      </Content>
    </Screen>
  )
}

/** 회차별 평균 마진 막대 (0 기준 좌우). 실력 지표가 아니라 그 회차의 결과라는 점을 라벨로 명시 */
export function MarginTrend({ points }: { points: MarginPoint[] }) {
  if (points.length === 0) return <Card><p className="text-sm text-stone-400">아직 기록된 쿼터가 없어요.</p></Card>
  const max = Math.max(3, ...points.map((m) => Math.abs(Number(m.avg_normalized_margin))))
  return (
    <Card className="space-y-1.5">
      <p className="text-[11px] text-stone-400">회차별 출전 쿼터의 평균 점수 차. 팀 결과라 개인 실력 그 자체는 아니에요.</p>
      {points.map((m) => {
        const v = Number(m.avg_normalized_margin)
        const w = Math.round((Math.abs(v) / max) * 50)
        return (
          <div key={m.event_id} className="flex items-center gap-2 text-xs">
            <span className="w-12 shrink-0 text-stone-500">{m.event_date.slice(5).replace('-', '/')}</span>
            <div className="relative h-4 flex-1 rounded bg-stone-100">
              <div className="absolute inset-y-0 left-1/2 w-px bg-stone-300" />
              <div className={`absolute inset-y-0.5 rounded ${v >= 0 ? 'left-1/2 bg-emerald-500' : 'right-1/2 bg-rose-500'}`} style={{ width: `${Math.max(w, v === 0 ? 0 : 2)}%` }} />
            </div>
            <span className={`w-12 shrink-0 text-right font-semibold ${v > 0 ? 'text-emerald-600' : v < 0 ? 'text-rose-600' : 'text-stone-500'}`}>{v > 0 ? '+' : ''}{v.toFixed(1)}</span>
            <span className="w-10 shrink-0 text-right text-stone-400">{m.wins}승{m.losses}패</span>
          </div>
        )
      })}
    </Card>
  )
}

const PAGE = 10

/** 목록을 10개씩 끊어 카드 안에서 페이지 이동 (최신순 목록 기준: ‹ 최근 / 이전 ›) */
export function Paged<T>({ items, render, unit = '개' }: { items: T[]; render: (item: T, i: number) => ReactNode; unit?: string }) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(items.length / PAGE))
  const cur = Math.min(page, pages - 1)
  return (
    <Card className="divide-y divide-stone-100 p-0">
      {pages > 1 && (
        <div className="flex items-center justify-between px-4 py-2 text-xs">
          <button disabled={cur === 0} onClick={() => setPage(cur - 1)} className="rounded-lg px-2 py-1 font-semibold text-navy-700 disabled:opacity-30">‹ 최근</button>
          <span className="text-stone-500">{cur * PAGE + 1}–{Math.min(items.length, (cur + 1) * PAGE)} / {items.length}{unit}</span>
          <button disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} className="rounded-lg px-2 py-1 font-semibold text-navy-700 disabled:opacity-30">이전 ›</button>
        </div>
      )}
      {items.slice(cur * PAGE, cur * PAGE + PAGE).map((it, i) => render(it, cur * PAGE + i))}
    </Card>
  )
}

/** 쿼터 기록 목록 — 10개씩 페이지 이동. 이긴 쿼터는 오렌지, 진 쿼터는 로즈 배지 */
export function QuarterList({ records }: { records: QuarterRecord[] }) {
  if (records.length === 0) return null
  return (
    <Paged items={records} unit="쿼터" render={(r) => {
        const win = r.raw_margin > 0
        return (
          <div key={`${r.event_id}-${r.quarter_no}`} className="flex items-center gap-3 px-4 py-2 text-xs">
            <span className="w-12 shrink-0 text-stone-500">{r.event_date.slice(5).replace('-', '/')}</span>
            <span className="w-10 shrink-0 font-semibold text-navy-900">{r.quarter_no}쿼터</span>
            <span className={`inline-flex w-12 shrink-0 items-center justify-center rounded-full py-0.5 text-[10px] font-semibold ${r.side === 'BLACK' ? 'bg-navy-900 text-white' : 'border border-stone-300 text-navy-900'}`}>{r.side === 'BLACK' ? '블랙' : '화이트'}</span>
            <span className="flex-1 text-stone-600">{r.my_score} : {r.their_score}{r.position ? ` · ${r.position}` : ''}</span>
            <span className={`inline-flex w-12 shrink-0 items-center justify-center rounded-full py-0.5 text-[11px] font-bold ${win ? 'bg-emerald-500 text-white' : r.raw_margin < 0 ? 'bg-rose-500 text-white' : 'bg-stone-200 text-stone-600'}`}>{r.raw_margin > 0 ? '+' : ''}{r.raw_margin}</span>
          </div>
        )
      }} />
  )
}
