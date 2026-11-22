/**
 * 로그인 전에 연 주소(초대 링크)는 로그인 뒤 그대로 열린다 (FR-01, docs/09 3-1).
 * 이메일 로그인에서는 로그인 화면의 가드가 뒤늦게 "홈으로"를 실행해 초대 링크를 덮어썼다(카카오 로그인은 가드 밖이라 괜찮았다).
 * React 가 실제로 그리는 순서에서만 드러나는 문제라 브라우저로 확인한다.
 */
import { test, expect } from '@playwright/test'

test('초대 링크를 연 채 이메일로 로그인하면 그 팀 가입 화면에 머문다', async ({ page }) => {
  await page.goto('/teams/join?code=CTMATE26')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('이메일').fill('m05@demo.com')
  await page.getByLabel('비밀번호').fill('demo1234')
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page.getByLabel('팀 코드', { exact: true })).toHaveValue('CTMATE26')
  await page.waitForTimeout(600)  // 뒤늦은 이동이 덮어쓰지 않는지 한 박자 기다린다
  await expect(page).toHaveURL(/\/teams\/join\?code=CTMATE26$/)
})
