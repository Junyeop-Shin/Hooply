/**
 * S-15 출전 명단 고치기 — 확정 배정에 없던 사람을 쿼터 기록에 넣을 수 있는지.
 * 저장은 하지 않는다(데모 데이터를 건드리지 않기 위해). 저장 경로는 백엔드 테스트가 덮는다.
 */
import { test, expect } from '@playwright/test'
import { EVENT, login, openEvent } from './helpers'

test('쿼터 기록: 명단에 없던 사람을 반대 팀에 넣을 수 있다', async ({ page }) => {
  await login(page)
  await openEvent(page, EVENT.LAST_WEEK)
  await page.getByRole('button', { name: /경기 기록 \d+쿼터/ }).click()
  await expect(page.getByRole('heading', { name: '경기 기록' })).toBeVisible()

  // 쿼터 길이는 1~10분만 받는다
  const dur = page.getByLabel('1쿼터 길이(분)')
  await expect(dur).toHaveAttribute('min', '1')
  await expect(dur).toHaveAttribute('max', '10')

  const whiteCount = async () => Number((await page.getByText(/^화이트 \d+명$/).innerText()).match(/\d+/)![0])
  const before = await whiteCount()

  // 새 멤버 추가는 쿼터 카드 맨 아래, 두 팀 공통
  await page.getByRole('button', { name: '＋ 새 멤버 추가' }).first().click()
  await expect(page.getByLabel('명단에 넣을 사람 찾기')).toBeVisible()
  // 화이트에 없는 사람 하나를 화이트 명단에 넣는다
  await page.getByRole('button', { name: '＋화이트' }).first().click()
  expect(await whiteCount()).toBe(before + 1)

  // 넣은 사람은 첫 쿼터의 화이트 '자기 팀' 칸에 바로 나온다
  const whiteOwn = page.locator('[data-roster="white-own"]').first()
  await expect(whiteOwn.locator('input[type=checkbox]')).toHaveCount(before + 1)
  // 팀을 옮긴 경우를 대비해 다른 팀 사람이 그 아래에 있다
  await expect(page.locator('[data-roster="white-other"]').first()).toBeVisible()
  await expect(page.getByText('다른 팀 · 옮겼으면 여기서 체크').first()).toBeVisible()

  // 처음 온 게스트 입력칸도 있다 (등록은 백엔드 테스트가 덮는다)
  await expect(page.getByLabel('새 게스트 이름')).toBeVisible()
})
