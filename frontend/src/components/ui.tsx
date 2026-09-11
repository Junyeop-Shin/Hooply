/**
 * 공통 UI 조각. 색 사용 규칙:
 *   primary(court 오렌지) = 화면당 하나뿐인 주요 액션
 *   secondary(navy)      = 보조 액션, 제목
 *   ghost                = 취소·뒤로 등 눈에 띄지 않아야 하는 액션
 * 터치 영역은 최소 44px (설계서 5.1절).
 */
import { useId, useState } from 'react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { API_ORIGIN } from '../api/client'
import type { ApprovalStatus, SkillGrade, TeamRole, TeamStatus } from '../api/types'

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
const variants: Record<Variant, string> = {
  primary: 'bg-court-500 text-white hover:bg-court-600 active:bg-court-700 shadow-sm',
  secondary: 'bg-navy-800 text-white hover:bg-navy-700 active:bg-navy-900',
  ghost: 'bg-transparent text-navy-700 hover:bg-navy-50',
  danger: 'bg-white text-rose-600 border border-rose-200 hover:bg-rose-50',
}

export function Button({
  variant = 'primary',
  full,
  loading,
  className,
  children,
  type = 'button',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; full?: boolean; loading?: boolean }) {
  // type 기본값이 'submit' 이면 form 안의 보조 버튼(불러오기 등)이 눌릴 때 폼이 제출된다. 제출 버튼만 type="submit" 을 명시한다
  return (
    <button
      type={type}
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-xl px-4 font-semibold transition',
        'min-h-11 text-[15px] disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        full && 'w-full',
        className,
      )}
    >
      {loading && <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
      {children}
    </button>
  )
}

export function Field({
  label,
  hint,
  error,
  id,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  // 라벨은 htmlFor 로, 힌트·오류는 aria-describedby 로 연결한다. 라벨로 감싸면 힌트까지 이름에 섞여
  // 스크린리더가 "제목 (선택) 비워 두면 날짜로 보여요" 를 한 덩어리로 읽는다
  const auto = useId()
  const inputId = id ?? auto
  const descId = `${inputId}-desc`
  const desc = error ?? hint
  return (
    <div className="block">
      <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium text-navy-800">{label}</label>
      <input
        {...input}
        id={inputId}
        aria-describedby={desc ? descId : undefined}
        aria-invalid={error ? true : undefined}
        className={cx(
          'block w-full rounded-xl border bg-white px-3.5 py-3 text-[15px] outline-none transition',
          'placeholder:text-stone-400 focus:ring-2 disabled:bg-stone-50 disabled:text-stone-400',
          error
            ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
            : 'border-stone-200 focus:border-court-400 focus:ring-court-100',
          input.className,
        )}
      />
      {desc && <p id={descId} className={cx('mt-1 text-xs', error ? 'text-rose-600' : 'text-stone-500')}>{desc}</p>}
    </div>
  )
}

export function Card({ className, children, onClick, label }: { className?: string; children: ReactNode; onClick?: () => void; label?: string }) {
  // 누를 수 있는 카드는 role·tabIndex·Enter/Space 를 붙여 키보드와 스크린리더로도 쓸 수 있게 한다
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      aria-label={onClick ? label : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
      className={cx(
        'rounded-2xl border border-stone-200 bg-white p-4 shadow-[0_1px_2px_rgba(20,33,61,0.04)]',
        onClick && 'cursor-pointer active:bg-stone-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-court-500',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function Alert({ kind = 'error', children }: { kind?: 'error' | 'info' | 'warn'; children: ReactNode }) {
  const styles = {
    error: 'bg-rose-50 text-rose-700 border-rose-200',
    info: 'bg-navy-50 text-navy-700 border-navy-100',
    warn: 'bg-amber-50 text-amber-800 border-amber-200',
  }[kind]
  return <div className={cx('rounded-xl border px-3.5 py-3 text-sm', styles)}>{children}</div>
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'court' | 'navy' | 'success' | 'warn'; children: ReactNode }) {
  const styles = {
    neutral: 'bg-stone-100 text-stone-600',
    court: 'bg-court-100 text-court-700',
    navy: 'bg-navy-100 text-navy-700',
    success: 'bg-emerald-100 text-emerald-700',
    warn: 'bg-amber-100 text-amber-800',
  }[tone]
  return <span className={cx('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', styles)}>{children}</span>
}

export function TeamStatusBadge({ status, approval }: { status: TeamStatus; approval?: ApprovalStatus }) {
  if (approval === 'REJECTED') return <Badge>승인 거절</Badge>
  if (approval === 'PENDING') return <Badge tone="warn">승인 대기</Badge>
  if (status === 'ACTIVE') return <Badge tone="success">활성</Badge>
  if (status === 'PENDING') return <Badge tone="warn">모집 중</Badge>
  return <Badge>보관됨</Badge>
}

/** 역할 배지 — 글자 수가 달라도 폭을 같게 해서 옆의 실력 배지가 세로로 정렬되게 한다 */
export function RoleBadge({ role }: { role: TeamRole }) {
  const styles = role === 'MANAGER' ? 'bg-court-100 text-court-700' : 'bg-navy-100 text-navy-700'
  return <span className={cx('inline-flex w-14 items-center justify-center rounded-full py-0.5 text-xs font-semibold', styles)}>{role === 'MANAGER' ? '매니저' : '플레이어'}</span>
}

/** 실력 등급 원형 배지. 등급 없음 = 데이터 부족 (5.4절 예외 시나리오) */
export function GradeDot({ grade }: { grade: SkillGrade | null }) {
  const tone: Record<SkillGrade, string> = {
    A: 'bg-court-500 text-white',
    B: 'bg-court-300 text-navy-900',
    C: 'bg-navy-200 text-navy-900',
    D: 'bg-stone-200 text-stone-700',
    E: 'bg-stone-100 text-stone-500',
  }
  return (
    <span
      title={grade ? `실력 등급 ${grade}` : '데이터 부족'}
      className={cx(
        'inline-flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-bold',
        grade ? tone[grade] : 'border border-dashed border-stone-300 text-stone-400',
      )}
    >
      {grade ?? '?'}
    </span>
  )
}

/** 프로필 사진이 있으면 보여 주고, 없거나 불러오지 못하면 이름 첫 글자로 돌아간다 (카카오 CDN 주소는 만료될 수 있다) */
export function Avatar({ name, src, size = 'md' }: { name: string; src?: string | null; size?: 'sm' | 'md' | 'lg' | 'xl' }) {
  const s = { sm: 'size-8 text-xs', md: 'size-10 text-sm', lg: 'size-14 text-lg', xl: 'size-20 text-2xl' }[size]
  const [failed, setFailed] = useState(false)
  // 서버가 주는 주소는 `/api/v1/users/…` 상대경로다. 프론트와 API 도메인이 다르면 API 쪽으로 붙여 준다
  const url = src && !failed ? (src.startsWith('/') ? `${API_ORIGIN}${src}` : src) : null
  return (
    <span className={cx('inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-navy-100 font-bold text-navy-700', s)}>
      {url
        ? <img src={url} alt="" className="size-full object-cover" loading="lazy" onError={() => setFailed(true)} />
        : name.slice(0, 1)}
    </span>
  )
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between px-1">
      <h2 className="text-sm font-bold tracking-wide text-stone-500">{children}</h2>
      {action}
    </div>
  )
}

export function EmptyState({ title, desc, action }: { title: string; desc?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-stone-300 bg-white/60 px-6 py-8 text-center">
      <span className="mb-1 h-1 w-8 rounded-full bg-court-300" />
      <p className="font-semibold text-navy-800">{title}</p>
      {desc && <p className="text-sm text-stone-500">{desc}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Spinner() {
  return (
    <div className="flex justify-center py-12">
      <span className="size-7 animate-spin rounded-full border-[3px] border-court-200 border-t-court-500" />
    </div>
  )
}
