/**
 * 팀 리더보드 — 참여율 · 출전 쿼터 (전원) / 잔차 누적 (매니저). 팀 화면 팀원 탭에서 진입.
 * 실력 수치를 순위로 공개하는 것은 갈등을 부르므로(9.2절 표시 정책) 플레이어에게는 참여 지표만 보여준다.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { teamsApi } from '../api/teams'
import type { LeaderboardMetric } from '../api/types'
import { Alert, Avatar, Card, GradeDot, Spinner } from '../components/ui'
import { Content, Screen, TopBar } from '../components/layout'

const LABEL: Record<LeaderboardMetric, string> = { attendance: '참여율', quarters: '출전 쿼터', residual: '기여 점수' }

export function LeaderboardPage() {
  const { teamId } = useParams()
  const id = Number(teamId)
  const team = useQuery({ queryKey: ['team', id], queryFn: () => teamsApi.get(id) })
  const isManager = team.data?.my_role === 'MANAGER'
  const [metric, setMetric] = useState<LeaderboardMetric>('attendance')
  const [period, setPeriod] = useState<string>('')
  const q = useQuery({ queryKey: ['team', id, 'leaderboard', metric, period], queryFn: () => teamsApi.leaderboard(id, metric, period || undefined) })
  const metrics: LeaderboardMetric[] = isManager ? ['attendance', 'quarters', 'residual'] : ['attendance', 'quarters']
  const now = new Date()
  const months = Array.from({ length: 3 }, (_, i) => { const d = new Date(now.getFullYear(), now.getMonth() - i, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` })

  return (
    <Screen>
      <TopBar title="리더보드" back={`/teams/${id}`} />
      <div className="grid border-b border-line bg-surface" style={{ gridTemplateColumns: `repeat(${metrics.length}, 1fr)` }}>
        {metrics.map((m) => (
          <button key={m} onClick={() => setMetric(m)} className={`min-h-11 text-sm font-semibold ${metric === m ? 'border-b-2 border-court-500 text-brand-ink' : 'text-faint'}`}>{LABEL[m]}</button>
        ))}
      </div>
      <Content>
        <div className="flex gap-1.5 overflow-x-auto px-1">
          {[['', '전체'], ...months.map((m) => [m, `${Number(m.slice(5))}월`])].map(([v, l]) => (
            <button key={v} onClick={() => setPeriod(v)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${period === v ? 'bg-navy-800 text-white' : 'bg-sunken text-muted'}`}>{l}</button>
          ))}
        </div>
        <p className="px-1 text-xs text-muted">
          {metric === 'attendance' ? '지난 일정 중 참석한 비율이에요. 가입 전 일정은 빼요.' : metric === 'quarters' ? '기록된 쿼터에 출전한 횟수예요.' : '예상보다 얼마나 더 벌었는지를 쌓은 값이에요. 매니저에게만 보여요.'}
        </p>
        {q.isLoading ? <Spinner /> : q.isError ? <Alert>불러오지 못했어요.</Alert> : (
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
            {q.data!.items.length === 0 && <p className="px-4 py-6 text-center text-sm text-faint">아직 집계할 일정이 없어요.</p>}
          </Card>
        )}
      </Content>
    </Screen>
  )
}
