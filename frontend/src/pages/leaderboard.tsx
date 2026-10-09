/**
 * 팀 리더보드 — 참석률 · 출전 쿼터 (전원) / 기여 점수 (매니저). 팀 화면 팀원 탭에서 진입.
 * 실력 수치를 순위로 공개하는 것은 갈등을 부르므로(9.2절 표시 정책) 플레이어에게는 참여 지표만 보여준다.
 *
 * 기간은 전체 또는 한 달을 고른다. 고를 수 있는 달은 서버가 알려 주는 "기록이 있는 달" 뿐이라
 * 빈 달을 골라 놓고 아무것도 안 나오는 상황이 생기지 않는다.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { teamsApi } from '../api/teams'
import type { LeaderboardMetric } from '../api/types'
import { Avatar, Card, GradeDot, LoadError, Spinner } from '../components/ui'
import { Content, Screen, TopBar } from '../components/layout'

const LABEL: Record<LeaderboardMetric, string> = { attendance: '참석률', quarters: '출전 쿼터', residual: '기여 점수' }
const HELP: Record<LeaderboardMetric, string> = {
  attendance: '지난 일정 중 참석한 비율이에요. 가입 전 일정은 빼요.',
  quarters: '기록된 쿼터에 출전한 횟수예요.',
  residual: '예상 점수 차보다 더 낸 점수를 쌓은 값이에요. 매니저에게만 보여요.',
}

/** "2026-09" → "2026년 9월" */
const monthLabel = (p: string) => `${p.slice(0, 4)}년 ${Number(p.slice(5))}월`

export function LeaderboardPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const team = useQuery({ queryKey: ['team', id], queryFn: () => teamsApi.get(id) })
  const isManager = team.data?.my_role === 'MANAGER'
  const [metric, setMetric] = useState<LeaderboardMetric>('attendance')
  const [period, setPeriod] = useState<string>('')
  // 일정에서 나오는 목록이라 'events' 아래에 둔다 — 일정을 만들거나 취소하면 함께 갱신된다
  const periods = useQuery({ queryKey: ['events', 'team', id, 'periods'], queryFn: () => teamsApi.leaderboardPeriods(id) })
  const q = useQuery({ queryKey: ['team', id, 'leaderboard', metric, period], queryFn: () => teamsApi.leaderboard(id, metric, period || undefined) })
  const metrics: LeaderboardMetric[] = isManager ? ['attendance', 'quarters', 'residual'] : ['attendance', 'quarters']
  const months = periods.data?.items ?? []

  return (
    <Screen>
      <TopBar title="리더보드" back={`/teams/${id}`} />
      <div role="tablist" className="grid border-b border-line bg-surface" style={{ gridTemplateColumns: `repeat(${metrics.length}, 1fr)` }}>
        {metrics.map((m) => (
          <button key={m} role="tab" aria-selected={metric === m} onClick={() => setMetric(m)} className={`min-h-11 text-sm font-semibold ${metric === m ? 'border-b-2 border-court-500 text-brand-ink' : 'text-muted'}`}>{LABEL[m]}</button>
        ))}
      </div>
      <Content>
        <div className="flex items-center gap-2 px-1">
          <label htmlFor="period" className="text-xs font-semibold text-muted">기간</label>
          <select
            id="period" value={period} onChange={(e) => setPeriod(e.target.value)}
            disabled={periods.isLoading}
            className="min-h-11 flex-1 rounded-xl border border-line-field bg-surface px-3 text-base font-semibold text-ink"
          >
            <option value="">전체</option>
            {months.map((p) => <option key={p} value={p}>{monthLabel(p)}</option>)}
          </select>
        </div>
        {!periods.isLoading && months.length === 0 && <p className="px-1 text-xs text-muted">지난 일정이 생기면 달을 고를 수 있어요.</p>}
        <p className="px-1 text-xs text-muted">{HELP[metric]}</p>
        {q.isLoading ? <Spinner /> : q.isError ? <LoadError message="순위를 불러오지 못했어요." onRetry={() => q.refetch()} retrying={q.isFetching} /> : (
          <Card className="divide-y divide-line p-0">
            {q.data!.items.map((e) => {
              const v = Number(e.value)
              return (
                <div key={e.player.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className={`w-6 text-center text-sm font-black ${e.rank <= 3 ? 'text-brand-ink' : 'text-faint'}`}>{e.rank}</span>
                  <Avatar name={e.player.display_name} src={e.player.profile_image_url} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink">{e.player.display_name}</p>
                    <p className="text-[11px] text-muted">{e.detail}</p>
                  </div>
                  {isManager && metric === 'residual' && <GradeDot grade={e.player.skill_grade} />}
                  <span className={`text-sm font-bold ${metric === 'residual' ? (v > 0 ? 'text-ok-ink' : v < 0 ? 'text-danger-ink' : 'text-muted') : 'text-ink'}`}>
                    {metric === 'attendance' ? `${Math.round(v * 100)}%` : metric === 'quarters' ? `${v}` : `${v > 0 ? '+' : ''}${v.toFixed(1)}`}
                  </span>
                </div>
              )
            })}
            {q.data!.items.length === 0 && <p className="px-4 py-6 text-center text-sm text-muted">지난 일정이 생기면 순위가 보여요.</p>}
          </Card>
        )}
      </Content>
    </Screen>
  )
}
