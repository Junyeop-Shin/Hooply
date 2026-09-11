import { expect, type Page } from '@playwright/test'

export const MANAGER = { email: 'manager@demo.com', password: 'demo1234' }
export const PLAYER = { email: 'm01@demo.com', password: 'demo1234' }

export async function login(page: Page, who = MANAGER) {
  await page.goto('/login')
  await page.getByLabel('이메일').fill(who.email)
  await page.getByLabel('비밀번호').fill(who.password)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('p', { hasText: /^일요 코트메이트/ }).first()).toBeVisible()
}

/** 홈 → 팀 → 일정 탭에서 n번째 "일요 정기전" 카드 (0 = 예정된 이번 주, 1 = 가장 최근 지난 회차) */
export async function openEvent(page: Page, nth: number) {
  await expect(page.getByText('일요 정기전').first()).toBeVisible()  // 일정 목록까지 로드돼 레이아웃이 안정된 뒤에 누른다
  await page.getByText('회원 20명').first().click()  // 내 팀 목록의 '일요 코트메이트' 카드 (일정 카드에도 팀 이름이 있어 회원 수로 고른다)
  await expect(page.getByRole('heading', { name: '일요 코트메이트' })).toBeVisible()
  await page.getByText('일요 정기전').nth(nth).click()
  await expect(page.getByRole('heading', { name: '일요 정기전' })).toBeVisible()
  await expect(page.getByText(/참석하시나요|참석 응답/)).toBeVisible()  // 응답 중이면 질문형, 끝난 일정이면 '참석 응답'
}
