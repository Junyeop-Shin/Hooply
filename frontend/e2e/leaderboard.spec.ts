/** 리더보드 — 기간 드롭다운에는 기록이 있는 달만 들어가고, 기여 점수가 기간에 따라 달라진다. */
import { test, expect } from '@playwright/test'
import { login } from './helpers'

test('리더보드: 달을 고르면 기여 점수가 그 달 값으로 바뀐다', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await page.getByRole('button', { name: '기록', exact: true }).click()
  await page.getByRole('button', { name: /^리더보드 더 보기/ }).click()
  await expect(page.getByRole('heading', { name: '리더보드' })).toBeVisible()

  const period = page.getByLabel('기간')
  await expect(period).toBeVisible()
  await expect(period.locator('option')).not.toHaveCount(1)  // 달 목록을 받아올 때까지 기다린다
  const options = await period.locator('option').allTextContents()
  expect(options[0]).toBe('전체')
  expect(options.length).toBeGreaterThan(1)
  for (const o of options.slice(1)) expect(o).toMatch(/^\d{4}년 \d{1,2}월$/)  // 년·월 표기

  await page.getByRole('button', { name: '기여 점수' }).click()
  const firstValue = () => page.locator('main >> text=/^[+-]?\\d+\\.\\d$/').first().innerText()
  const all = await firstValue()
  // 기록이 있는 가장 최근 달을 고르면 전체와 다른 값이 나온다 (예전에는 늘 같은 값이었다)
  await period.selectOption(options[1].replace(/(\d{4})년 (\d{1,2})월/, (_, y, m) => `${y}-${String(m).padStart(2, '0')}`))
  await expect(page.locator('main >> text=/^[+-]?\\d+\\.\\d$/').first()).not.toHaveText(all)
})
