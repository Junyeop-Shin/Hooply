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
 * 예정 일정이 가까운 순으로 먼저 오고(이번 주부터 5건, UPCOMING_WEEKS), 그 뒤에 지난 회차가 최근 순으로 온다.
 * 일정 탭은 5개씩 페이지로 나뉘므로 지난주 회차는 2쪽 첫 칸이다.
 */
export const EVENT = { THIS_WEEK: 0, LAST_WEEK: 5 } as const
const EVENTS_PAGE = 5  // frontend/src/pages/team.tsx 와 같다

/** 홈 → 팀 → 일정 탭에서 n번째 "일요 정기전" 카드. 순서는 `EVENT` 참고 */
export async function openEvent(page: Page, nth: number) {
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()  // 카드의 접근성 이름 — 시드 인원수에 의존하지 않는다
  await expect(page.getByRole('heading', { name: '일요 코트메이트' })).toBeVisible()
  for (let p = 0; p < Math.floor(nth / EVENTS_PAGE); p++) await page.getByRole('button', { name: '다음 ›' }).click()
  await page.getByText('일요 정기전').nth(nth % EVENTS_PAGE).click()
  await expect(page.getByRole('heading', { name: '일요 정기전' })).toBeVisible()
  // 응답 중이면 질문형, 끝난 일정이면 '참석 응답', 배정이 확정된 일정이면 화면이 곧 팀 배정 결과
  await expect(page.getByText(/참석하시나요|참석 응답|팀 배정 결과/).first()).toBeVisible()
}
