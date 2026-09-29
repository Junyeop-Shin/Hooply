/** 전술 탭 · 전술판 (docs/07 S-28 · S-29) — 목록 22개(하프코트 20 · 인바운드 2), 전술판 단계 이동, 없는 전술 안내. */
import { test, expect } from '@playwright/test'
import { EVENT, login, openEvent, PLAYER } from './helpers'

test('전술 탭: 전술 22개 목록 → 전술판에서 단계를 넘기며 본다', async ({ page }) => {
  await login(page, PLAYER)
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await page.getByRole('button', { name: '전술', exact: true }).click()

  await expect(page.getByRole('heading', { name: '전술 목록' })).toBeVisible()
  await expect(page.getByRole('button', { name: /전술판 보기$/ })).toHaveCount(22)
  // 그날 배정이 확정돼 있으면 위에 추천 전술이 늦게 붙어 목록이 밀린다 — 다 불러온 뒤에 누른다
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '혼즈 전술판 보기' }).click()

  await expect(page.getByRole('img', { name: '혼즈 전술판' })).toBeVisible()
  const caption = page.locator('p[aria-live="polite"]')
  await expect(caption).toContainText('1/4')
  await page.getByRole('button', { name: '다음 단계' }).click()
  await expect(caption).toContainText('2/4')
  await page.getByRole('button', { name: '이전 단계' }).click()
  await expect(caption).toContainText('1/4')
  // 역할 목록: 슬롯 5개
  await expect(page.getByText('볼 핸들러')).toBeVisible()
  await expect(page.getByText('스크리너(팝)')).toBeVisible()
})

test('없는 전술 주소는 안내만 한다', async ({ page }) => {
  await login(page, PLAYER)
  await page.goto('/tactics/nope')
  await expect(page.getByText('없는 전술이에요.')).toBeVisible()
})

test('배정이 끝난 일정(팀원): 팀 배정 결과만 — 공유·참석 현황은 없다', async ({ page }) => {
  await login(page, PLAYER)
  await openEvent(page, EVENT.LAST_WEEK)
  await expect(page.getByRole('heading', { name: '팀 배정 결과' })).toBeVisible()
  await expect(page.getByText(/내 팀 · 팀|팀 블랙|팀 화이트/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '카카오톡 공유' })).toHaveCount(0)  // 공유는 매니저만
  await expect(page.getByText('참석 현황 · 관리')).toHaveCount(0)  // 누가 불참했는지는 팀원에게 필요 없다
})

test('배정이 끝난 일정(매니저): 공유 · 추천 전술 · 접힌 참석 관리', async ({ page }) => {
  await login(page)
  await openEvent(page, EVENT.LAST_WEEK)
  await expect(page.getByRole('button', { name: '카카오톡 공유' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '이 팀에 맞는 전술' })).toBeVisible()
  await page.getByRole('button', { name: /참석 현황 · 관리/ }).click()
  await expect(page.getByText(/참석하시나요|참석 응답/).first()).toBeVisible()
})
