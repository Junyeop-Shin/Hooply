/**
 * 화면 머리(히어로) 배경의 코트 선 — 위에서 본 반코트(3점 라인 · 페인트 존 · 자유투 원 · 백보드와 림).
 * 남색 면 위에 옅게 깔리는 장식이라 스크린리더에는 숨기고 누르는 것도 막지 않는다 (docs/11 규칙 3).
 * 부모는 `relative overflow-hidden` 이어야 하고, 그 위의 글자는 `relative` 로 올려 둔다. 위치 · 크기는 className 으로.
 */
export function CourtLines({ className = '' }: { className?: string }) {
  return (
    <svg
      aria-hidden="true" viewBox="0 0 260 230" fill="none" stroke="currentColor" strokeWidth="2"
      className={`pointer-events-none absolute text-white/[0.13] ${className}`}
    >
      <path d="M30 0V70a100 100 0 0 0 200 0V0" />
      <rect x="90" y="0" width="80" height="112" />
      <circle cx="130" cy="112" r="40" />
      <path d="M106 14h48" />
      <circle cx="130" cy="27" r="9" />
    </svg>
  )
}
