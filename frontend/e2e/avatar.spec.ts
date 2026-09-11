import { expect, test } from '@playwright/test'
import { login, MANAGER } from './helpers'

// 16x16 PNG (실제 이미지여야 브라우저가 캔버스로 줄일 수 있다)
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFklEQVR4nGN4li1LEmIY1TCqYfhqAABc724QodhNOQAAAABJRU5ErkJggg==', 'base64')

test('프로필 사진 추가 → 팀원 목록 아바타에 반영 → 삭제', async ({ page }) => {
  page.on('dialog', (d) => d.accept())
  await login(page, MANAGER)
  await page.goto('/me')

  // 이전 실행이 남긴 사진이 있으면 먼저 지운다 (반복 실행 가능하게)
  const remove = page.getByRole('button', { name: '프로필 사진 삭제' })
  if (await remove.isVisible()) await remove.click()
  await expect(page.getByRole('button', { name: '프로필 사진 추가하기' })).toBeVisible()

  await page.setInputFiles('input[type=file]', { name: 'me.png', mimeType: 'image/png', buffer: PNG })
  await expect(page.getByRole('button', { name: '프로필 사진 바꾸기' })).toBeVisible({ timeout: 15000 })

  // 올린 사진은 실제로 받아진다 (캐시 헤더 포함)
  const src = await page.locator('img[src*="avatar"]').first().getAttribute('src')
  expect(src).toContain('/api/v1/users/')
  const res = await page.request.get(src!)
  expect(res.status()).toBe(200)
  expect(res.headers()['content-type']).toContain('image/')

  // 팀원 목록의 동그란 아바타에도 같은 사진이 들어간다
  await page.goto('/teams/1')
  await page.getByRole('button', { name: /팀원 \d+/ }).click()
  await expect(page.locator('img[src*="avatar"]').first()).toBeVisible({ timeout: 15000 })

  // 지우면 이름 첫 글자로 돌아간다
  await page.goto('/me')
  await page.getByRole('button', { name: '프로필 사진 삭제' }).click()
  await expect(page.getByRole('button', { name: '프로필 사진 추가하기' })).toBeVisible()
  await expect(page.locator('img[src*="avatar"]')).toHaveCount(0)
})
