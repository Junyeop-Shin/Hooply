/** S-01 로그인 · S-02 회원가입 (FR-01). 카카오 버튼은 백엔드 스켈레톤이라 안내만 띄운다. */
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuthStore } from '../store/auth'
import { Alert, Button, Field } from '../components/ui'
import { Screen } from '../components/layout'

function Brand() {
  return (
    <div className="flex flex-col items-center gap-3 pb-6 pt-14 text-center">
      <span className="flex size-16 items-center justify-center rounded-3xl bg-court-500 text-3xl font-black tracking-tight text-white shadow-lg shadow-brand-line">H</span>
      <div>
        <h1 className="text-3xl font-black tracking-[0.12em] text-ink">HOOPLY</h1>
        <p className="mt-1 text-sm font-semibold text-brand-ink">농구를 즐기는 새로운 방식</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">사람을 모으고, 기록을 쌓고,<br />그날의 실력에 맞는 팀을 만들어요.</p>
      </div>
    </div>
  )
}

/** 카카오 인가 URL 을 받아 이동. state 와 모드(login/link)는 sessionStorage 에 두었다가 콜백 화면에서 대조한다 */
export async function startKakao(mode: 'login' | 'link', onError: (m: string) => void) {
  try {
    const { url, state } = await authApi.kakaoLoginUrl()
    sessionStorage.setItem('kakao_state', state)
    sessionStorage.setItem('kakao_mode', mode)
    window.location.href = url
  } catch (e) {
    onError(e instanceof ApiError ? e.message : '카카오 로그인을 시작하지 못했어요.')
  }
}

function KakaoButton() {
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <div className="space-y-2">
      <button
        type="button"
        disabled={busy}
        onClick={() => { setBusy(true); startKakao('login', (m) => { setErr(m); setBusy(false) }) }}
        className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[#FEE500] font-semibold text-[#191919] active:brightness-95 disabled:opacity-60"
      >
        <span className="inline-block size-4 rounded-full bg-[#191919]" aria-hidden />카카오로 시작하기
      </button>
      {err && <Alert>{err}</Alert>}
    </div>
  )
}

/** /auth/kakao/callback — 카카오가 돌려보낸 code·state 를 백엔드에 넘겨 로그인(또는 계정 연결)을 끝낸다 */
export function KakaoCallbackPage() {
  const nav = useNavigate()
  const login = useAuthStore((s) => s.login)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search)
    const code = q.get('code'), state = q.get('state')
    const saved = sessionStorage.getItem('kakao_state'), mode = sessionStorage.getItem('kakao_mode') ?? 'login'
    sessionStorage.removeItem('kakao_state'); sessionStorage.removeItem('kakao_mode')
    if (q.get('error')) { setErr(q.get('error_description') ?? '카카오 로그인이 취소됐어요.'); return }
    if (!code || !state || state !== saved) { setErr('로그인 요청이 만료됐거나 올바르지 않아요. 다시 시도해 주세요.'); return }
    ;(async () => {
      try {
        if (mode === 'link') { await authApi.kakaoLink(code, state); nav('/me', { replace: true }); return }
        const pair = await authApi.kakaoCallback(code, state)
        login(pair)
        nav('/', { replace: true })  // 새 가입자는 홈에서 시작 안내 팝업을 본다
      } catch (e) { setErr(e instanceof ApiError ? e.message : '카카오 로그인에 실패했어요.') }
    })()
  }, [nav, login])
  return (
    <Screen className="px-6">
      <Brand />
      {err ? (
        <div className="space-y-3">
          <Alert>{err}</Alert>
          <Button full variant="secondary" onClick={() => nav('/login', { replace: true })}>로그인 화면으로</Button>
        </div>
      ) : (
        <p className="text-center text-sm text-muted">카카오 계정을 확인하고 있어요…</p>
      )}
    </Screen>
  )
}

export function LoginPage() {
  const nav = useNavigate()
  const setTokens = useAuthStore((s) => s.login)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      setTokens(await authApi.login(email, password))
      nav('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '로그인에 실패했어요.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Screen className="px-6">
      <Brand />
      <KakaoButton />
      <div className="my-5 flex items-center gap-3 text-xs text-faint">
        <span className="h-px flex-1 bg-line" />또는<span className="h-px flex-1 bg-line" />
      </div>
      <form onSubmit={submit} className="space-y-3">
        <Field label="이메일" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
        <Field label="비밀번호" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" full loading={loading}>로그인</Button>
      </form>
      <div className="mt-6 flex justify-center gap-4 text-sm text-muted">
        <Link to="/password/forgot" className="hover:text-ink-2">비밀번호 찾기</Link>
        <span className="text-faint">|</span>
        <Link to="/signup" className="font-semibold text-brand-ink">회원가입</Link>
      </div>
      <p className="mt-3 text-center text-xs text-faint"><Link to="/help" className="underline underline-offset-2 hover:text-ink-2">도움말 · 문의</Link></p>
    </Screen>
  )
}

export function SignupPage() {
  const nav = useNavigate()
  const setTokens = useAuthStore((s) => s.login)
  const [form, setForm] = useState({ email: '', password: '', name: '', nickname: '', height_cm: '' })
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setFieldErrors({})
    setLoading(true)
    try {
      const pair = await authApi.signup({
        email: form.email,
        password: form.password,
        name: form.name,
        nickname: form.nickname || undefined,
        height_cm: form.height_cm ? Number(form.height_cm) : undefined,
      })
      setTokens(pair)
      nav('/', { replace: true }) // 가입 직후 홈 — 시작 안내 팝업에서 설문·팀 가입으로 안내한다
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === 'VALIDATION_ERROR') {
          const fe: Record<string, string> = {}
          err.details.forEach((d) => {
            if (d.field) fe[d.field.replace(/^body\./, '')] = d.reason
          })
          setFieldErrors(fe)
        }
        setError(err.message)
      } else setError('회원가입에 실패했어요.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Screen className="px-6 pb-8">
      <div className="pt-10 pb-6">
        <h1 className="text-2xl font-black text-ink">회원가입</h1>
        <p className="mt-1 text-sm text-muted">가입 후 2분짜리 실력 설문이 이어져요.</p>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <Field label="이메일" type="email" value={form.email} onChange={set('email')} error={fieldErrors.email} required />
        <Field label="비밀번호" type="password" value={form.password} onChange={set('password')} hint="8자 이상" error={fieldErrors.password} required />
        <Field label="이름" value={form.name} onChange={set('name')} error={fieldErrors.name} required />
        <Field label="닉네임 (선택)" value={form.nickname} onChange={set('nickname')} hint="팀원에게 보이는 이름. 비우면 이름을 써요." />
        <Field label="키 (cm)" type="number" inputMode="numeric" value={form.height_cm} onChange={set('height_cm')} placeholder="178" hint="골밑 적성 계산에만 쓰이고 다른 팀원에게 보이지 않아요." error={fieldErrors.height_cm} />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" full loading={loading} className="mt-2">가입하고 설문 시작</Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        이미 계정이 있나요? <Link to="/login" className="font-semibold text-brand-ink">로그인</Link>
      </p>
    </Screen>
  )
}
