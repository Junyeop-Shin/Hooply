import { defineConfig, devices } from '@playwright/test'

/**
 * E2E — 실제 백엔드 + 데모 데이터(seed_demo) 위에서 핵심 흐름만 확인한다.
 * 로컬: docker compose up (web 5173 / api 8000) 후 `npm run test:e2e`.
 * CI: .github/workflows/ci.yml 이 postgres·백엔드·vite preview(4173)를 띄우고 BASE_URL 을 넘긴다.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  workers: 1,  // 스펙들이 한 DB 를 같이 쓴다 — 동시에 돌면 다른 스펙이 만든 전술 · 확정이 섞여 개수가 어긋난다
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:5173',
    ...devices['Pixel 7'],
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',  // 날짜 계산이 러너 시간대(UTC)에 흔들리지 않게 실제 사용 환경으로 고정
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'mobile-chromium', use: { ...devices['Pixel 7'] } }],
})
