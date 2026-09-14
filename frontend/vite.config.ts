/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 개발 중에는 /api 요청을 FastAPI(8000)로 프록시해 CORS 없이 같은 출처처럼 쓴다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 라이브러리는 앱 코드와 분리해 둔다 — 화면을 고쳐도 브라우저가 라이브러리 청크는 다시 받지 않는다
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id: string) => (id.includes('node_modules') ? 'vendor' : undefined),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  // 단위·컴포넌트 테스트 (Vitest + Testing Library). E2E 는 playwright.config.ts
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
