import { expect, test } from '@playwright/test'
import { login, PLAYER } from './helpers'

// 플레이어 계정으로 주요 화면을 돌며 남의 등급(A~E 원형 배지)이 보이는지 센다
test('플레이어에게는 남의 실력 등급이 보이지 않고 내 등급만 보인다', async ({ page }) => {
  const seen: string[] = []
  page.on('response', async (r) => {
    const u = new URL(r.url()).pathname
    if (!u.startsWith('/api/v1') || !r.ok()) return
    try {
      const t = await r.text()
      if (/"skill_grade":\s*"[A-E]"/.test(t)) seen.push(u)
    } catch { /* 이미지 등 */ }
  })
  await login(page, PLAYER)
  await page.goto('/teams/1')
  await page.getByRole('button', { name: /팀원 \d+/ }).click()
  await page.waitForTimeout(800)
  await page.goto('/teams/1/leaderboard')
  await page.waitForTimeout(800)
  // 일정 id 는 시드 생성 순서: 지난 회차 10개(1~10) → 이번 주(11) (backend/scripts/seed_demo.py)
  await page.goto('/events/11')           // 이번 주 일정: 참석자 목록
  await page.waitForTimeout(1000)
  await page.goto('/events/10/assignment') // 지난주 확정 배정
  await page.waitForTimeout(800)
  await page.goto('/events/10/vote')       // 투표 후보
  await page.waitForTimeout(800)
  await page.goto('/me')
  await page.waitForTimeout(800)
  // 등급이 실려도 되는 곳은 "내 것" 뿐이다 (내 프로필 · 내 통계)
  const leaked = [...new Set(seen)].filter((u) => u !== '/api/v1/me/profile' && !/^\/api\/v1\/players\/\d+\/stats$/.test(u))
  expect(leaked, `플레이어에게 남의 등급이 실려 왔다: ${leaked.join(', ')}`).toEqual([])
  // 내 등급은 보여야 한다
  expect([...new Set(seen)]).toContain('/api/v1/me/profile')
})
