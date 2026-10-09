/** 기록 탭 — 내 추세 · 월간 코트 마진 · 배지가 한 화면에 있고, 랭킹은 접었다 펼 수 있다. */
import { test, expect } from '@playwright/test'
import { login } from './helpers'

test('기록 탭: 세 섹션이 보이고 월간 랭킹은 접었다 펼 수 있다', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await page.getByRole('tab', { name: '기록', exact: true }).click()

  await expect(page.getByRole('heading', { name: '내 추세' })).toBeVisible()
  await expect(page.getByRole('heading', { name: /이달의 점수 차 순위/ })).toBeVisible()
  await expect(page.getByRole('heading', { name: '배지' })).toBeVisible()
  // 데모 매니저는 10주치 기록이 있어 추세 그래프와 순위 표가 나온다
  await expect(page.getByRole('img', { name: '활동일별 평균 점수 차' })).toBeVisible()
  const period = page.getByLabel('달')
  await expect(period).toBeVisible()
  await expect(page.locator('main >> text=/^[+-]\\d+\\.\\d$/').first()).toBeVisible()

  // 접기 → 한 줄 요약만, 펼치기 → 다시 표. 접힘은 새로고침 뒤에도 유지된다
  await page.getByRole('button', { name: '접기 ▴' }).click()
  await expect(period).toBeHidden()
  await page.reload()
  await page.getByRole('tab', { name: '기록', exact: true }).click()
  await expect(page.getByLabel('달')).toBeHidden()
  await page.getByRole('button', { name: '펼치기 ▾' }).first().click()
  await expect(page.getByLabel('달')).toBeVisible()

  // 배지: 칸 12개(묶음 4 + 단일 8). 묶음 칸은 단계가 붙고, 누르면 동·은·금 시트가 올라온다
  await expect(page.getByText(/획득 \d+\/20/)).toBeVisible()
  await expect(page.getByRole('button', { name: /자세히 보기$/ })).toHaveCount(12)
  await expect(page.getByRole('button', { name: '설문 완료 자세히 보기' })).toBeVisible()
  await page.getByRole('button', { name: /^출전 · (동|은|금) 자세히 보기$/ }).click()
  const sheet = page.getByRole('dialog', { name: '출전 배지' })
  await expect(sheet).toBeVisible()
  await expect(sheet.getByText('동 · 출전 10쿼터')).toBeVisible()
  await expect(sheet.getByText('금 · 출전 100쿼터')).toBeVisible()
  await sheet.getByRole('button', { name: '닫기' }).click()
  await expect(sheet).toBeHidden()
})
