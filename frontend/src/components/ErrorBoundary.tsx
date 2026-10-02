/**
 * 렌더링 중 예외가 나면 화면 전체가 하얗게 비는 대신 안내와 복구 버튼을 보여 준다.
 * React 는 클래스 컴포넌트로만 오류 경계를 만들 수 있다.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { isChunkLoadError } from '../lib/stale-chunk'

interface State { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('화면을 그리다 오류가 났어요', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    const stale = isChunkLoadError(this.state.error)  // 새로고침을 한 번 했는데도 예전 파일을 부르는 경우
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-page px-6 text-center">
        <p className="text-lg font-bold text-ink">{stale ? '새 버전이 나왔어요' : '화면을 불러오지 못했어요'}</p>
        <p className="text-sm text-muted">{stale ? '새로고침하면 새 버전으로 열려요.' : '잠시 문제가 생겼어요. 새로고침하면 대부분 해결돼요.'}</p>
        <p className="max-w-full truncate text-[11px] text-faint">{this.state.error.message}</p>
        <div className="mt-2 flex gap-2">
          <button onClick={() => location.reload()} className="min-h-11 rounded-xl bg-brand px-4 text-sm font-semibold text-on-brand">새로고침</button>
          <button onClick={() => { this.setState({ error: null }); location.assign('/') }} className="min-h-11 rounded-xl border border-line bg-surface px-4 text-sm font-semibold text-ink">홈으로</button>
        </div>
      </div>
    )
  }
}
