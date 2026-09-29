/** 전술 편집기 · AI 역할 태깅 · 전술 댓글 (docs/07 S-30, FR-57 ~ FR-60). 만든 전술은 끝에 지워 다른 테스트의 목록 개수를 바꾸지 않는다. */
import { test, expect, type Page } from '@playwright/test'
import { login } from './helpers'

/** 편집 코트의 (x, y) — 0~1 코트 좌표 */
async function tapCourt(page: Page, x: number, y: number) {
  const court = page.getByRole('group', { name: '전술 편집 코트' })
  const box = (await court.boundingBox())!
  await court.click({ position: { x: box.width * x, y: box.height * y } })
}

async function slot(page: Page, n: number) {
  await page.getByRole('group', { name: '전술 편집 코트' }).getByRole('button', { name: `${n}번`, exact: true }).click()
}

test('매니저가 픽앤롤을 그려 저장하고, 역할을 붙이고, 댓글을 단 뒤 지운다', async ({ page }) => {
  page.on('dialog', (d) => d.accept())
  await login(page)
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await page.getByRole('button', { name: '전술', exact: true }).click()
  await page.getByRole('link', { name: '+ 새 전술 만들기' }).click()

  await page.getByLabel('전술 이름').fill('E2E 픽앤롤')
  // 1단계: 5번이 1번에게 스크린
  await page.getByRole('tab', { name: '+ 단계' }).click()
  await slot(page, 5)
  await page.getByRole('button', { name: '스크린', exact: true }).click()
  await slot(page, 1)
  await tapCourt(page, 0.56, 0.62)
  await expect(page.getByText('5번 스크린 → 1번').first()).toBeVisible()
  // 2단계: 1번 드리블 · 5번 컷
  await page.getByRole('tab', { name: '+ 단계' }).click()
  await slot(page, 1)
  await page.getByRole('button', { name: '드리블', exact: true }).click()
  await tapCourt(page, 0.7, 0.4)
  await slot(page, 5)
  await page.getByRole('button', { name: '컷', exact: true }).click()
  await tapCourt(page, 0.52, 0.14)
  // 3단계: 1번 → 5번 패스, 4단계: 5번 슛
  await page.getByRole('tab', { name: '+ 단계' }).click()
  await slot(page, 1)
  await page.getByRole('button', { name: '패스', exact: true }).click()
  await slot(page, 5)
  await page.getByRole('tab', { name: '+ 단계' }).click()
  await slot(page, 5)
  await page.getByRole('button', { name: '슛', exact: true }).click()

  // 검사를 통과하면 미리 보기(상대 수비 포함)가 뜨고, 역할이 움직임에서 뽑힌다
  await expect(page.getByRole('heading', { name: '미리 보기' })).toBeVisible()
  // 상대 수비는 편집기에서만 고른다 — 미리 보기 전술판은 고른 대로 고정
  await page.getByRole('radiogroup', { name: '스크린 대응' }).getByRole('radio', { name: '스위치' }).click()
  await expect(page.getByText('맨투맨 수비 · 스크린 스위치').first()).toBeVisible()
  await expect(page.getByLabel('5번 역할')).toHaveValue('screener_roll')
  await page.getByRole('button', { name: 'AI로 역할 붙이기' }).click()  // CI 에는 키가 없어 규칙 결과
  await expect(page.getByText(/AI가 전술의 의도까지|AI를 쓸 수 없어/)).toBeVisible()

  await page.getByRole('button', { name: '전술 저장' }).click()
  await expect(page.getByRole('heading', { name: 'E2E 픽앤롤' })).toBeVisible()
  await expect(page.getByText('스크리너(롤)')).toBeVisible()
  await expect(page.getByText('맨투맨 수비 · 스크린 스위치')).toBeVisible()
  await expect(page.getByRole('radiogroup', { name: '상대 수비' })).toHaveCount(0)  // 전술판에는 고르는 칸이 없다

  // 댓글
  await page.getByLabel('댓글', { exact: true }).fill('5번 롤이 빨라야 해요')
  await page.getByRole('button', { name: '남기기' }).click()
  await expect(page.getByText('5번 롤이 빨라야 해요')).toBeVisible()

  // 고치기 → 지우기
  await page.getByRole('link', { name: '고치기' }).click()
  await expect(page.getByLabel('전술 이름')).toHaveValue('E2E 픽앤롤')
  await page.getByRole('button', { name: '전술 지우기' }).click()
  await expect(page.getByRole('heading', { name: '일요 코트메이트' })).toBeVisible()
})
