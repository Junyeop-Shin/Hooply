import { expect, type Page } from '@playwright/test'

export const MANAGER = { email: 'manager@demo.com', password: 'demo1234' }
export const PLAYER = { email: 'm01@demo.com', password: 'demo1234' }

export async function login(page: Page, who = MANAGER) {
  await page.goto('/login')
  await page.getByLabel('이메일').fill(who.email)
  await page.getByLabel('비밀번호').fill(who.password)
  await page.getByRole('button', { name: '로그인' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('button', { name: '일요 코트메이트 팀 열기' })).toBeVisible()
}

/**
 * 팀 일정 탭의 "일요 정기전" 카드 순서 (backend/scripts/seed_demo.py 기준).
 * 예정 일정이 가까운 순으로 먼저 오고(이번 주 · 다음 주 · 2주 뒤), 그 뒤에 지난 회차가 최근 순으로 온다.
 */
export const EVENT = { THIS_WEEK: 0, LAST_WEEK: 3 } as const

/** 홈 → 팀 → 일정 탭에서 n번째 "일요 정기전" 카드. 순서는 `EVENT` 참고 */
export async function openEvent(page: Page, nth: number) {
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()  // 카드의 접근성 이름 — 시드 인원수에 의존하지 않는다
  await expect(page.getByRole('heading', { name: '일요 코트메이트' })).toBeVisible()
  await page.getByText('일요 정기전').nth(nth).click()
  await expect(page.getByRole('heading', { name: '일요 정기전' })).toBeVisible()
  await expect(page.getByText(/참석하시나요|참석 응답/)).toBeVisible()  // 응답 중이면 질문형, 끝난 일정이면 '참석 응답'
}
