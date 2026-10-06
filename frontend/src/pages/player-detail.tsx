/**
 * 매니저용 선수 실력 지표 화면 (S-08 → 지표 보기) + S-17 기록 조각(MarginTrend · QuarterList 는 프로필에서도 재사용).
 * 설문 사전값 · 매니저 정렬 순위 · 코트 마진(잔차) 이력 · 피어 투표 지목 수를 한 화면에서 보여 "왜 이 등급인가"를 설명한다.
 * 실력 수치는 매니저/ADMIN 에게만 내려온다 (13.1절 Q3). 원시 마진은 실력이 아니라 결과다 (9.1절) — 그렇게 표기한다.
 */
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { peerApi } from '../api/peer'
import { Alert, Avatar, Badge, Card, GradeDot, SectionTitle, Spinner } from '../components/ui'
import { MarginTrend, Paged, QuarterList } from '../components/stats'
import { Content, Screen, TopBar } from '../components/layout'

const SOURCE_LABEL: Record<string, string> = {
  SURVEY: '가입 설문', MANAGER_SORT: '매니저가 매긴 순서', RESIDUAL: '경기 기록', PEER_VOTE: '경기 후 투표',
  MANAGER_ADJUST: '매니저가 직접 조정', ADMIN_ADJUST: '관리자가 직접 조정', MERGE: '게스트 기록 이어받기',
}
const PRIOR_LABEL: Record<string, string> = { SURVEY: '설문으로 정함', MANAGER: '매니저가 정함', DEFAULT: '팀 평균 (아직 정보 없음)' }
const AXIS_LABEL: Record<string, string> = { shooting: '슛', ball_handling: '드리블', passing: '패스', defense: '수비', rebound_post: '골밑', stamina: '체력' }
const AXIS_LEVEL: Record<'HIGH' | 'MID' | 'LOW', string> = { HIGH: '팀 상위', MID: '팀 중간', LOW: '팀 하위' }

export function PlayerDetailPage() {
  const { teamId, playerId } = useParams()
  const pid = Number(playerId)
  const q = useQuery({ queryKey: ['stats', pid], queryFn: () => peerApi.stats(pid), retry: false })
  if (q.isLoading) return <Screen><TopBar title="실력 자세히 보기" back={`/teams/${teamId}/members`} /><Spinner page /></Screen>
  if (!q.data) return <Screen><TopBar title="실력 자세히 보기" back={`/teams/${teamId}/members`} /><Content><Alert>불러오지 못했어요. 매니저만 볼 수 있어요.</Alert></Content></Screen>
  const s = q.data
  const p = s.player
  const signed = (v: string | null | undefined) => (v === null || v === undefined ? '—' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(1)}`)
  const conf = s.skill_confidence === null ? 0 : Number(s.skill_confidence)
  const wins = s.margin_trend.reduce((a, m) => a + m.wins, 0)

  return (
    <Screen>
      <TopBar tone="navy" title="실력 자세히 보기" back={`/teams/${teamId}/members`} />
      <div className="bg-navy-800 px-4 pb-4 text-white">
        <div className="flex items-center gap-3">
          <Avatar name={p.display_name} src={p.profile_image_url} size="lg" />
          <div className="min-w-0 flex-1">
            <p className="text-lg font-bold">{p.display_name} {p.kind === 'GUEST' && <Badge>게스트</Badge>}</p>
            <p className="text-xs text-bar-sub">{p.playable_positions.length ? p.playable_positions.join(' · ') : '포지션 미입력'} · 참석 {s.events_attended}회 · 출전 {s.quarters_played}쿼터</p>
          </div>
          <GradeDot grade={s.skill_grade} />
        </div>
      </div>
      <Content>
        {/* 종합 */}
        <Card>
          <div className="flex items-baseline justify-between">
            <p className="text-sm font-bold text-ink">실력 점수</p>
            <p className="text-2xl font-black text-ink">{signed(s.skill_overall ?? s.prior_overall)}<span className="ml-1 text-xs font-normal text-faint">점 / 쿼터</span></p>
          </div>
          <p className="mt-1 text-xs text-muted">이 사람이 코트에 있을 때 팀이 한 쿼터에 더 얻는 점수예요. 0이 팀 평균이에요.</p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
            <div className="rounded-lg bg-surface-2 py-2"><p className="text-[10px] text-muted">시작 점수</p><p className="font-bold text-ink">{signed(s.prior_overall)}</p><p className="text-[10px] text-faint">{s.prior_source ? PRIOR_LABEL[s.prior_source] ?? s.prior_source : '—'}</p></div>
            <div className="rounded-lg bg-surface-2 py-2"><p className="text-[10px] text-muted">경기 반영 후</p><p className="font-bold text-ink">{signed(s.skill_overall)}</p><p className="text-[10px] text-faint">{s.skill_overall === null ? '아직 반영 전' : `경기로 ${signed(s.cumulative_residual)}`}</p></div>
            <div className="rounded-lg bg-surface-2 py-2"><p className="text-[10px] text-muted">정보 충분도</p><p className="font-bold text-ink">{Math.round(conf * 100)}%</p><p className="text-[10px] text-faint">{conf < 0.3 ? '아직 부족' : conf < 0.6 ? '보통' : '충분'}</p></div>
          </div>
        </Card>

        {/* 근거 3가지 */}
        <section>
          <SectionTitle>이 점수가 나온 이유</SectionTitle>
          <div className="space-y-2">
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">가입 설문</p>
                <p className="text-xs text-muted">{s.prior_source === 'SURVEY' ? '구력·슛 거리·드리블·수비 이해도와 동호회 안에서 본인이 고른 위치를 합쳐 정했어요' : s.prior_source === 'MANAGER' ? '데려온 사람이 고른 실력 단계를 팀 안 순위로 바꿔 정했어요' : '설문 응답이 없어 팀 평균에서 시작했어요'}</p>
              </div>
              <span className="text-sm font-bold text-ink">{signed(s.prior_overall)}</span>
            </Card>
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">매니저가 매긴 순서</p>
                <p className="text-xs text-muted">{s.manager_rank ? `${s.manager_rank.total}명 중 ${s.manager_rank.rank_no}번째 · 설문과 반반으로 섞어 시작 점수를 정해요` : '아직 순서에 들어가지 않았어요 (설문만 반영)'}</p>
              </div>
              {s.manager_rank && <span className="text-sm font-bold text-ink">{s.manager_rank.rank_no}<span className="text-xs font-normal text-faint">/{s.manager_rank.total}</span></span>}
            </Card>
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">경기 기록</p>
                <p className="text-xs text-muted">{s.quarters_played === 0 ? '출전 기록이 없어요' : `출전 ${s.quarters_played}쿼터 · 이긴 쿼터 ${wins}개 · 예상보다 얼마나 더 벌었는지를 쌓아 반영해요 (처음 두 일정은 빼요)`}</p>
              </div>
              <span className={`text-sm font-bold ${Number(s.cumulative_residual ?? 0) < 0 ? 'text-danger-ink' : 'text-ink'}`}>{signed(s.cumulative_residual)}</span>
            </Card>
            <Card className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink">경기 후 투표</p>
                <p className="text-xs text-muted">"다음에 같이 뛰고 싶은 사람"으로 지목 {s.play_again_received ?? 0}회 · 상호 지목 {s.play_again_mutual ?? 0}쌍. 실력 점수에는 넣지 않고, 친화도 우선으로 팀을 나눌 때만 써요.</p>
              </div>
            </Card>
          </div>
        </section>

        {Object.keys(s.skill_axes).length > 0 && (
          <section>
            <SectionTitle>세부 능력 · 팀 내 위치 (설문 기준)</SectionTitle>
            <Card className="space-y-2">
              {Object.keys(s.skill_axes).map((k) => {
                const r = s.skill_axes_rank?.[k]
                const pct = r?.percentile ?? null
                const tone = r?.level === 'HIGH' ? 'bg-brand' : r?.level === 'LOW' ? 'bg-faint' : 'bg-navy-800'
                return (
                  <div key={k} className="flex items-center gap-3">
                    <span className="w-9 shrink-0 text-xs font-semibold text-ink">{AXIS_LABEL[k] ?? k}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-sunken">
                      {pct !== null && <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(pct, 4)}%` }} />}
                    </div>
                    <span className={`w-16 shrink-0 text-right text-[11px] font-semibold ${r?.level === 'HIGH' ? 'text-brand-ink' : r?.level === 'LOW' ? 'text-faint' : 'text-muted'}`}>
                      {r?.level ? AXIS_LEVEL[r.level] : '비교 인원 부족'}
                    </span>
                  </div>
                )
              })}
              <p className="pt-1 text-[11px] text-muted">
                {Object.values(s.skill_axes_rank ?? {}).some((r) => r.level)
                  ? `같은 팀 ${Object.values(s.skill_axes_rank)[0]?.sample ?? 0}명의 설문과 비교한 위치예요. 막대가 길수록 팀에서 앞쪽이에요.`
                  : '설문에 답한 팀원이 4명 이상이면 팀 내 위치가 보여요.'}
              </p>
            </Card>
          </section>
        )}

        <section>
          <SectionTitle>일정별 점수 차</SectionTitle>
          <MarginTrend points={s.margin_trend} />
        </section>
        <section>
          <SectionTitle>최근 쿼터</SectionTitle>
          <QuarterList records={s.recent_quarters} />
        </section>

        {s.history.length > 0 && (
          <section>
            <SectionTitle>점수가 바뀐 기록</SectionTitle>
            <Paged items={s.history} render={(h, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-xs">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-ink">{SOURCE_LABEL[h.source] ?? h.source}</p>
                    <p className="truncate text-muted">{h.reason ?? ''} · {new Date(h.created_at).toLocaleDateString('ko-KR')}</p>
                  </div>
                  <span className="text-muted">{signed(h.before_value)} → <b className={Number(h.delta ?? 0) < 0 ? 'text-danger-ink' : 'text-ink'}>{signed(h.after_value)}</b></span>
                </div>
              )} />
          </section>
        )}
      </Content>
    </Screen>
  )
}
