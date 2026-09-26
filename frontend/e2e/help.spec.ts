/** 도움말 — 내 프로필에서 들어가고, 로그인하지 않아도 열린다. 문의 주소가 보인다. */
import { test, expect } from '@playwright/test'
import { login } from './helpers'

test('도움말: 내 프로필에서 열고 주제를 펼칠 수 있다', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: '프로필' }).click()
  await page.getByRole('button', { name: '도움말 · 문의' }).click()
  await expect(page.getByRole('heading', { name: '도움말' })).toBeVisible()
  // 프로필 맨 아래에서 들어와도 맨 위부터 보인다
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  // 첫 주제(실력과 공개 범위)는 펼쳐져 있다
  await expect(page.getByText('내 실력은 누가 볼 수 있나요?')).toBeVisible()
  // 접힌 주제를 누르면 펼쳐진다
  await expect(page.getByText('팀은 어떻게 나누나요?')).toBeHidden()
  await page.getByText('팀 배정', { exact: true }).click()
  await expect(page.getByText('팀은 어떻게 나누나요?')).toBeVisible()
  await expect(page.getByText('sjt015@naver.com')).toBeVisible()
})

test('도움말: 로그인하지 않아도 로그인 화면에서 열린다', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('link', { name: '도움말 · 문의' }).click()
  await expect(page.getByRole('heading', { name: '도움말' })).toBeVisible()
  await expect(page.getByText('sjt015@naver.com')).toBeVisible()
})
