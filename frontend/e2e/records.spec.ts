/** 기록 탭 — 내 추세 · 월간 코트 마진 · 배지가 한 화면에 있고, 랭킹은 접었다 펼 수 있다. */
import { test, expect } from '@playwright/test'
import { login } from './helpers'

test('기록 탭: 세 섹션이 보이고 월간 랭킹은 접었다 펼 수 있다', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await page.getByRole('button', { name: '기록', exact: true }).click()

  await expect(page.getByRole('heading', { name: '내 추세' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '월간 코트 마진' })).toBeVisible()
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
  await page.getByRole('button', { name: '기록', exact: true }).click()
  await expect(page.getByLabel('달')).toBeHidden()
  await page.getByRole('button', { name: '펼치기 ▾' }).first().click()
  await expect(page.getByLabel('달')).toBeVisible()

  // 배지: 설문을 마친 계정이라 '설문 완료' 는 획득 상태
  await expect(page.getByText('설문 완료')).toBeVisible()
  await expect(page.getByText(/획득 \d+\/19/)).toBeVisible()
})
