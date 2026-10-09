import { expect, test } from '@playwright/test'
import { EVENT, login, openEvent, PLAYER } from './helpers'

test.describe('핵심 흐름', () => {
  test('로그인 → 홈에 팀과 다가오는 일정이 보인다', async ({ page }) => {
    await login(page)
    await expect(page.getByText('다가오는 일정')).toBeVisible()
    await expect(page.getByText('일요 정기전').first()).toBeVisible()
  })

  test('매니저: 팀 배정 실행 → 후보안 3개 → 확정', async ({ page }) => {
    await login(page)
    await openEvent(page, EVENT.THIS_WEEK)
    await page.getByRole('button', { name: /팀 나누러 가기|팀 다시 나누기/ }).click()
    await expect(page.getByText('대기 칸')).toBeVisible()
    const run = page.getByRole('button', { name: '3가지 배정안 만들기' })
    await expect(run).toBeEnabled()
    await run.click()
    await expect(page.getByRole('tab', { name: /실력 우선/ })).toBeVisible()
    await expect(page.getByRole('tab', { name: /친화도 우선/ })).toBeVisible()
    await expect(page.getByRole('tab', { name: /^종합/ })).toBeVisible()
    await expect(page.getByText('이렇게 나눈 이유')).toBeVisible()
    await page.getByRole('button', { name: '이 배정안으로 확정' }).click()
    await page.getByRole('dialog', { name: /배정안으로 확정할까요/ }).getByRole('button', { name: '확정' }).click()  // 확인 시트
    await expect(page.getByRole('heading', { name: '팀 배정 결과' })).toBeVisible()
    await expect(page.getByText(/블랙 팀/).first()).toBeVisible()

    // 구성표 이미지 공유 — 카카오 키·OS 공유 시트가 없는 CI 브라우저에서는 PNG 내려받기로 떨어진다
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '카카오톡 공유' }).click()
    const file = await download
    expect(file.suggestedFilename()).toMatch(/^팀배정-\d{4}-\d{2}-\d{2}\.png$/)
    await expect(page.getByRole('status').getByText('이미지를 저장했어요. 카카오톡에 첨부해 주세요.')).toBeVisible()  // 공유 결과는 토스트
  })

  test('매니저: 지난 회차 경기 기록 화면에 쿼터가 보인다', async ({ page }) => {
    await login(page)
    await openEvent(page, EVENT.LAST_WEEK)
    await page.getByRole('button', { name: '경기 기록 보기 · 고치기' }).click()
    await expect(page.getByRole('heading', { name: '경기 기록' })).toBeVisible()
    await expect(page.getByText('1쿼터', { exact: false }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /\d+쿼터 고쳐서 저장/ })).toBeVisible()
  })

  test('플레이어: 배정 결과에는 실력 수치가 없고 내 프로필에 기록이 보인다', async ({ page }) => {
    await login(page, PLAYER)
    await page.goto('/me')
    await page.getByRole('button', { name: '일요 코트메이트' }).click()  // 두 팀 소속 → 기록이 있는 팀 선택
    await expect(page.getByText('출전 쿼터', { exact: true })).toBeVisible()  // 프로필·기록 로딩 후
    await expect(page.getByRole('heading', { name: /^기록/ })).toBeVisible()
    await expect(page.getByText(/^실력 /)).toHaveCount(0)
  })
})
