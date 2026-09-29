import { chromium, devices } from '@playwright/test'
const S = '/private/tmp/claude-501/-Users-junyeop-Desktop-SKALA-----17----------mini-project-AI----------/be71a95a-ffd3-4bbd-98aa-c6b510ce5664/scratchpad'
const b = await chromium.launch()
const errs = []
async function session(email) {
  const ctx = await b.newContext({ ...devices['iPhone 13'], baseURL: 'http://localhost:5173' })
  const p = await ctx.newPage()
  p.on('pageerror', (e) => errs.push(email + ': ' + e.message))
  await p.goto('/login')
  await p.getByLabel('이메일').fill(email)
  await p.getByLabel('비밀번호').fill('demo1234')
  await p.getByRole('button', { name: '로그인' }).click()
  await p.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await p.getByRole('button', { name: '전술', exact: true }).click()
  return p
}
// 팀원: 추천이 보인다
const p = await session('m01@demo.com')
await p.getByText('추천 전술').first().waitFor()
await p.waitForTimeout(600)
await p.screenshot({ path: S + '/v2-player-tab.png', fullPage: true })
// 재생 스트레스: 8개 전술 × 재생 3번 (움직임 켠 상태)
const keys = ['high_pnr','horns','weave','pistol','floppy','ucla','post_split','zone_131']
for (const k of keys) {
  await p.goto('/tactics/' + k + '?event=11')
  await p.getByRole('img', { name: /전술판/ }).waitFor()
  for (let r = 0; r < 3; r++) {
    await p.getByRole('button', { name: '재생', exact: true }).click()
    await p.waitForTimeout(250 + r * 400)
    await p.getByRole('button', { name: '일시정지' }).click().catch(() => {})
    await p.getByRole('button', { name: '재생', exact: true }).click().catch(() => {})
    await p.getByRole('button', { name: '재생 속도 1배' }).click().catch(() => {})
    await p.waitForTimeout(300)
    await p.getByRole('button', { name: '처음' }).click().catch(() => {})
  }
  const broken = await p.getByText('화면을 불러오지 못했어요').count()
  if (broken) errs.push('broken on ' + k)
}
await p.goto('/tactics/high_pnr?event=11')
await p.getByRole('img', { name: /전술판/ }).waitFor()
await p.evaluate(() => window.scrollTo(0, 500))
await p.screenshot({ path: S + '/v2-player-board.png' })
await p.goto('/events/11/assignment')
await p.getByText('오늘 추천 전술').waitFor()
await p.getByText('오늘 추천 전술').scrollIntoViewIfNeeded()
await p.screenshot({ path: S + '/v2-adopted.png' })
// 매니저
const m = await session('manager@demo.com')
await m.getByText('추천 전술').first().waitFor()
await m.waitForTimeout(600)
await m.screenshot({ path: S + '/v2-manager-tab.png', fullPage: true })
await m.getByRole('button', { name: /전술판에서 보기/ }).first().click()
await m.getByRole('img', { name: /전술판/ }).waitFor()
await m.getByRole('button', { name: /2번 자리 선수 고르기/ }).first().click()
await m.getByRole('dialog').getByRole('button', { name: /벤치/ }).first().click()
await m.waitForTimeout(300)
await m.screenshot({ path: S + '/v2-manager-edit.png' })
console.log('errors', errs)
await b.close()
