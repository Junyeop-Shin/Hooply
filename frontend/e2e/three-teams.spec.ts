/** 3팀 배정 (참석이 15명을 넘으면 "3팀으로 나누기") — 데모의 이번 주 일정은 16명 참석. 배정은 실행하지 않아 다른 테스트에 영향이 없다. */
import { test, expect } from '@playwright/test'
import { EVENT, login, openEvent } from './helpers'

test('참석 16명이면 3팀으로 나누기를 체크해 블랙 · 화이트 · 레드 세 칸이 된다', async ({ page }) => {
  await login(page)
  await openEvent(page, EVENT.THIS_WEEK)
  // 앞선 테스트가 배정을 확정했을 수 있어(버튼이 "재배정하기") 주소로 바로 간다
  await page.goto(`${new URL(page.url()).pathname}/assign`)
  await expect(page.getByText('3팀으로 나누기')).toBeVisible()
  await expect(page.getByText(/레드 \(0명\)/)).toHaveCount(0)
  await page.getByText('3팀으로 나누기').click()
  await expect(page.getByText(/레드 \(0명\)/)).toBeVisible()
  await expect(page.getByText(/6·5·5명씩|5·5·6명씩|6·6·5명씩|\d·\d·\d명씩/)).toBeVisible()
  await expect(page.getByRole('button', { name: '3팀으로 3가지 배정안 만들기' })).toBeEnabled()
  // 다시 끄면 두 칸
  await page.getByText('3팀으로 나누기').click()
  await expect(page.getByText(/레드 \(0명\)/)).toHaveCount(0)
})
