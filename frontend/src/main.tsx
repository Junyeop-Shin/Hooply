import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './queryClient'
import './index.css'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastHost } from './components/toast'
import { ConfirmHost } from './components/confirm-sheet'
import { reloadForNewVersion } from './lib/stale-chunk'

// 미리 불러오기(modulepreload · CSS)가 예전 파일 이름으로 실패할 때도 새 버전을 받는다 (lazy 화면은 App.tsx 에서)
window.addEventListener('vite:preloadError', (e) => { if (reloadForNewVersion()) e.preventDefault() })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
          <ToastHost />
          <ConfirmHost />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
