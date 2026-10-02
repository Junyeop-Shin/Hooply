/**
 * 시작 안내 — 새 가입자 팝업 → 경로 선택 → 체크리스트(실제 데이터로 판정, 막힌 단계는 대기 중) · 기능별 첫 안내.
 * tutorial-player / tutorial-manager 는 seed_demo 가 막 가입한 상태(PENDING)로 만든다. 데모 팀 코드는 CTMATE26 고정.
 */
import { test, expect } from '@playwright/test'
import { login } from './helpers'

const PASSWORD = 'demo1234'
async function loginAs(page: import('@playwright/test').Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('이메일').fill(email)
  await page.getByLabel('비밀번호').fill(PASSWORD)
  await page.getByRole('button', { name: '로그인', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
}

test('팀원 경로: 팝업 → 코드로 가입하면 다음 단계가 열린다', async ({ page }) => {
  await loginAs(page, 'tutorial-player@demo.com')
  const prompt = page.getByRole('dialog', { name: '처음이시죠?' })
  await expect(prompt).toBeVisible()
  await prompt.getByRole('button', { name: '안내 받기' }).click()
  await expect(prompt).toBeHidden()
  // 할 일이 있는 칸만 밝게 — 먼저 경로 선택 칸, 고르면 첫 할 일 칸
  await expect(page.getByRole('dialog', { name: '먼저 하나만 골라 주세요' })).toBeVisible()
  await page.getByRole('button', { name: /네, 받았어요/ }).click()
  await expect(page.getByRole('dialog', { name: '먼저 하나만 골라 주세요' })).toBeHidden()
  await expect(page.getByText('0/4 완료')).toBeVisible()
  await expect(page.getByRole('dialog', { name: '다음 할 일이에요' })).toContainText('팀 코드로 가입')
  // 팀이 없으니 내 위치·참석 응답은 대기 중
  await expect(page.getByText('대기 중')).toHaveCount(2)

  await page.getByRole('link', { name: '코드 넣기' }).click()
  // 들어간 화면에서도 해야 할 칸만 밝게
  await expect(page.getByRole('dialog', { name: '팀 코드 넣기' })).toBeVisible()
  await page.getByLabel('팀 코드', { exact: true }).fill('CTMATE26')
  await page.getByRole('button', { name: '가입하기' }).click()
  await expect(page).toHaveURL(/self-rank/)  // 가입하면 바로 내 위치 문항으로 간다
  await page.goto('/')
  // 가입했으니 1단계 완료, 내 위치는 할 수 있게, 참석 응답은 이번 주 일정으로 바로 열린다. 다음 할 일(설문)이 밝아진다
  await expect(page.getByText('1/4 완료')).toBeVisible()
  const nextTip = page.getByRole('dialog', { name: '다음 할 일이에요' })
  await expect(nextTip).toContainText('실력·포지션 설문')
  await nextTip.getByRole('button', { name: '알겠어요' }).click()
  await expect(nextTip).toBeHidden()
  await page.reload()
  await expect(page.getByText('1/4 완료')).toBeVisible()
  await expect(nextTip).toBeHidden()  // 같은 단계는 한 번만 밝힌다
  await expect(page.getByRole('link', { name: '답하기', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: '응답하기', exact: true })).toBeVisible()
  // 닫으면 다시 뜨지 않는다
  await page.getByRole('button', { name: '시작 안내 닫기' }).click()
  await expect(page.getByText('1/4 완료')).toBeHidden()
  await page.reload()
  await expect(page.getByRole('button', { name: '시작 안내 닫기' })).toBeHidden()
})

test('매니저 경로: 팀을 만들면 팀원 모집 진행도와 대기 중인 일정 단계가 보인다', async ({ page }) => {
  await loginAs(page, 'tutorial-manager@demo.com')
  await page.getByRole('dialog', { name: '처음이시죠?' }).getByRole('button', { name: '안내 받기' }).click()
  await page.getByRole('button', { name: /아니요/ }).click()
  await page.getByRole('link', { name: '팀 만들기' }).first().click()
  await page.getByLabel('팀 이름', { exact: true }).fill('튜토리얼 팀')
  await page.getByRole('button', { name: '팀 코드 발급받기' }).click()
  await expect(page.getByText('팀이 만들어졌어요')).toBeVisible()
  await page.goto('/')
  await expect(page.getByText(/팀원 1\/5명/)).toBeVisible()
  await expect(page.getByText('첫 일정 등록')).toBeVisible()
  await expect(page.getByText('팀이 활성화되면 열려요.')).toBeVisible()
})

test('기능별 첫 안내: 한 번 닫으면 다시 뜨지 않는다', async ({ page }) => {
  await login(page)  // 데모 매니저 — 팝업 없이 첫 안내만 본다
  await expect(page.getByRole('dialog', { name: '처음이시죠?' })).toBeHidden()
  await page.getByRole('button', { name: '일요 코트메이트 팀 열기' }).click()
  await page.getByRole('tab', { name: '기록', exact: true }).click()
  const tip = page.getByRole('note', { name: '기록 탭에서 볼 수 있는 것' })
  await expect(tip).toBeVisible()
  await tip.getByRole('button', { name: '알겠어요' }).click()
  await expect(tip).toBeHidden()
  await page.reload()
  await page.getByRole('tab', { name: '기록', exact: true }).click()
  await expect(page.getByRole('heading', { name: '내 추세' })).toBeVisible()
  await expect(page.getByRole('note', { name: '기록 탭에서 볼 수 있는 것' })).toBeHidden()
})
