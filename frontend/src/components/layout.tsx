/**
 * 화면 뼈대. 모바일 폭(max 28rem)으로 가운데 정렬하고, 로그인 후 화면은 하단 탭바를 붙인다.
 * 설계서 5.1절: 주요 액션은 하단 고정, 역할별 진입점은 홈 카드로 분리.
 */
import { useEffect, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'

export function Screen({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`mx-auto flex min-h-full w-full max-w-md flex-col ${className}`}>{children}</div>
}

/** 뒤로 가기 — SPA 안에서 이전 화면이 있으면 그리로(history), 새로고침·직접 진입이면 fallback 경로로 */
export function useGoBack() {
  const nav = useNavigate()
  const loc = useLocation()
  return (fallback: string) => {
    // 앱 안에서 쌓인 히스토리가 있으면 진짜 뒤로 간다. from 을 push 하면 팀 ↔ 일정이 서로를 계속 쌓아 무한히 오가므로 쓰지 않는다.
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (idx > 0) { nav(-1); return }
    // 새로고침·딥링크(히스토리 없음): 진입 화면이 알려준 경로 → 없으면 기본 경로. replace 라 되돌아올 항목을 만들지 않는다
    const from = (loc.state as { from?: string } | null)?.from
    nav(from ?? fallback, { replace: true })
  }
}

/**
 * 흐름이 끝나 상위 화면으로 돌아갈 때(확정 · 저장 · 지우기 뒤) — 거쳐 온 화면 depth 개를 히스토리에서 되감는다.
 * 그 화면으로 새로 이동(push · replace)하면 거쳐 온 화면이 히스토리에 남아, 뒤로가 조건 설정 · 수정 화면으로 되돌아가거나
 * 같은 화면이 두 번 나온다. 되감을 히스토리가 없으면(새로고침 · 딥링크) 경로로 바꿔치기한다.
 */
export function useFinish() {
  const nav = useNavigate()
  return (fallback: string, depth: number) => {
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (idx >= depth) nav(-depth)
    else nav(fallback, { replace: true })
  }
}

export function TopBar({
  title,
  back,
  right,
  tone = 'light',
  beforeBack,
}: {
  title: ReactNode
  back?: boolean | string
  right?: ReactNode
  tone?: 'light' | 'navy'
  /** 뒤로 가기 전에 물어볼 것이 있으면(저장 안 한 입력 등) — false 를 돌려주면 머문다 */
  beforeBack?: () => boolean | Promise<boolean>
}) {
  const nav = useNavigate()
  const goBack = useGoBack()
  const dark = tone === 'navy'
  // 탭 · 방문 기록 · 스크린리더가 화면을 구분할 수 있게 (제목이 글자일 때만)
  useEffect(() => { if (typeof title === 'string') document.title = `${title} · HOOPLY` }, [title])
  return (
    <header
      className={`sticky top-0 z-10 flex h-14 items-center gap-2 px-3 ${
        dark ? 'bg-bar text-bar-ink' : 'border-b border-line bg-surface text-ink'
      }`}
    >
      {back ? (
        <button
          onClick={async () => {
            if (beforeBack && !(await beforeBack())) return
            if (typeof back === 'string') goBack(back)
            else nav(-1)
          }}
          className="-ml-0.5 flex size-11 shrink-0 items-center justify-center rounded-full text-xl active:bg-black/10"
          aria-label="뒤로"
        >
          ‹
        </button>
      ) : (
        <span className="w-2" />
      )}
      <h1 className="flex-1 truncate text-lg font-bold">{title}</h1>
      {right}
    </header>
  )
}

export function Content({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <main className={`flex-1 space-y-4 px-4 py-4 ${className}`}>{children}</main>
}

/** 화면 하단 고정 액션 영역 (5.1절 한 손 조작). 헤더와 같이 배경은 불투명 — iOS Safari(WebKit)에서 반투명 배경은
 * 아래 글자가 그대로 비쳐, 비활성(반투명) 버튼 위로 겹쳐 보였다 (docs/07 O7) */
export function BottomAction({ children }: { children: ReactNode }) {
  return (
    <div className="safe-bottom sticky bottom-0 border-t border-line bg-surface px-4 pt-3">
      {children}
    </div>
  )
}

const tabs = [
  { to: '/', label: '홈', icon: (
    <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11.5 12 4l9 7.5" /><path d="M5.5 10.5V20h13v-9.5" /><path d="M10 20v-5h4v5" /></svg>
  ) },
  { to: '/me', label: '프로필', icon: (
    <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="4" /><path d="M4.5 20a7.5 7.5 0 0 1 15 0" /></svg>
  ) },
]

/** 하단 탭 — 홈 / 프로필. 활성 탭은 코트 오렌지, 위에 짧은 바 */
export function TabBar() {
  return (
    <nav aria-label="주 메뉴" className="safe-bottom sticky bottom-0 z-10 grid grid-cols-2 border-t border-line bg-surface">
      {tabs.map((t) => (
        <NavLink
          key={t.to}
          to={t.to}
          end={t.to === '/'}
          className={({ isActive }) =>
            `relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold ${
              isActive ? 'text-brand-ink' : 'text-muted'
            }`
          }
        >
          {({ isActive }) => (
            <>
              {isActive && <span className="absolute top-0 h-0.5 w-10 rounded-b-full bg-brand" />}
              {t.icon}
              {t.label}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
