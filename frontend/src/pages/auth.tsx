/** S-01 로그인 · S-02 회원가입 (FR-01). 주 경로는 카카오, 이메일은 보조. */
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError, errorMessage } from '../api/client'
import { useAuthStore } from '../store/auth'
import { peekReturnTo, takeReturnTo } from '../lib/return-to'
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
    onError(errorMessage(e, '카카오 로그인을 시작하지 못했어요.'))
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
  const [welcome, setWelcome] = useState<string | null>(null)  // 카카오로 처음 온 사람 — 카톡 닉네임(팀에 보일 이름 기본값)
  useEffect(() => {
    const q = new URLSearchParams(window.location.search)
    const code = q.get('code'), state = q.get('state')
    const saved = sessionStorage.getItem('kakao_state'), mode = sessionStorage.getItem('kakao_mode') ?? 'login'
    sessionStorage.removeItem('kakao_state'); sessionStorage.removeItem('kakao_mode')
    if (q.get('error')) { setErr("카카오 로그인을 취소했어요. 다시 하려면 '카카오로 시작하기'를 눌러 주세요."); return }
    if (!code || !state || state !== saved) { setErr("로그인 시간이 지났어요. '카카오로 시작하기'를 다시 눌러 주세요."); return }
    ;(async () => {
      try {
        if (mode === 'link') { await authApi.kakaoLink(code, state); nav('/me', { replace: true }); return }
        const pair = await authApi.kakaoCallback(code, state)
        login(pair)
        if (pair.is_new) {
          // 처음 온 사람: 팀에 보일 이름을 정하고, 이메일로 가입한 계정이 있으면 빈 계정이 하나 더 생긴 것이라 바로잡게 한다 (docs/09 3-2 · 3-3)
          const me = await authApi.me().catch(() => null)
          setWelcome(me?.nickname ?? me?.name ?? '')
          return
        }
        nav(takeReturnTo() ?? '/', { replace: true })  // 초대 · 투표 링크로 왔으면 그 화면으로
      } catch (e) { setErr(errorMessage(e, '카카오 로그인에 실패했어요.')) }
    })()
  }, [nav, login])
  if (welcome !== null) return <KakaoWelcome initialName={welcome} />
  return (
    <Screen>
      <main className="flex flex-1 flex-col px-6">
      <Brand />
      {err ? (
        <div className="space-y-3">
          <Alert>{err}</Alert>
          <Button full variant="secondary" onClick={() => nav('/login', { replace: true })}>로그인 화면으로</Button>
        </div>
      ) : (
        <p className="text-center text-sm text-muted">카카오 계정을 확인하고 있어요…</p>
      )}
      </main>
    </Screen>
  )
}

/** 카카오로 처음 온 사람 — ① 팀원 목록 · 배정표에 보일 이름(기본은 카톡 닉네임) ② 이메일로 가입한 계정이 이미 있으면
 * 방금 생긴 빈 계정을 지우고 이메일 로그인 → 카카오 연결로 안내한다. 탈퇴하면 카카오 연결도 풀려서 다시 연결할 수 있다. */
function KakaoWelcome({ initialName }: { initialName: string }) {
  const nav = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const [name, setName] = useState(initialName)
  const [busy, setBusy] = useState<'go' | 'undo' | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const go = async (e: FormEvent) => {
    e.preventDefault()
    setBusy('go'); setErr(null)
    try {
      // 팀에 보이는 이름은 '닉네임 → 이름' 순이라 닉네임을 비워 이 이름이 보이게 한다 (닉네임은 내 정보에서 다시 넣을 수 있다)
      await authApi.updateMe({ name: name.trim(), nickname: null })
      nav(peekReturnTo() ? '/survey' : '/', { replace: true })  // 초대 링크로 왔으면 설문 → 그 링크(흐름 A), 아니면 홈의 시작 안내
    } catch (ex) { setErr(errorMessage(ex, '이름을 저장하지 못했어요.')); setBusy(null) }
  }
  const undo = async () => {
    setBusy('undo'); setErr(null)
    try {
      await authApi.deleteMe()
      logout()
      nav('/login', { replace: true, state: { notice: "방금 만든 카카오 계정은 지웠어요. 이메일로 로그인한 뒤 내 정보에서 '카카오 연결'을 눌러 주세요. 그다음부터는 카카오로 로그인할 수 있어요." } })
    } catch (ex) { setErr(errorMessage(ex, '계정을 정리하지 못했어요.')); setBusy(null) }
  }
  return (
    <Screen>
      <main className="flex flex-1 flex-col px-6">
        <Brand />
        <form onSubmit={go} className="space-y-4">
          <div>
            <p className="text-lg font-bold text-ink">반가워요! 카카오로 가입했어요</p>
            <p className="text-sm text-muted">팀원 목록 · 배정표 · 기록에 보일 이름을 확인해 주세요. 팀원이 알아볼 수 있게 실명을 권해요.</p>
          </div>
          <Field label="팀에 보일 이름" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={50} required />
          {err && <Alert>{err}</Alert>}
          <Button type="submit" full loading={busy === 'go'} disabled={!name.trim() || busy !== null}>이 이름으로 시작하기</Button>
        </form>
        <div className="mt-6 rounded-2xl bg-surface-2 p-4">
          <p className="text-sm font-semibold text-ink">이메일로 가입한 HOOPLY 계정이 있나요?</p>
          <p className="mt-1 text-xs text-muted">그렇다면 계정이 하나 더 생긴 거예요. 방금 만든 계정을 지우고, 이메일로 로그인해 카카오를 연결하면 기존 기록 그대로 카카오로 들어올 수 있어요.</p>
          <Button variant="secondary" full className="mt-3 text-sm" loading={busy === 'undo'} disabled={busy !== null} onClick={undo}>이메일 계정이 있어요</Button>
        </div>
      </main>
    </Screen>
  )
}

export function LoginPage() {
  const nav = useNavigate()
  const notice = (useLocation().state as { notice?: string } | null)?.notice
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
      nav(takeReturnTo() ?? '/', { replace: true })  // 초대 · 투표 링크로 왔으면 그 화면으로
    } catch (err) {
      setError(errorMessage(err, '로그인에 실패했어요.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Screen>
      <main className="flex flex-1 flex-col px-6">
      <Brand />
      {notice && <div className="mb-4"><Alert kind="info">{notice}</Alert></div>}
      <KakaoButton />
      <div className="my-5 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" />또는<span className="h-px flex-1 bg-line" />
      </div>
      <form onSubmit={submit} className="space-y-3">
        <Field label="이메일" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
        <Field label="비밀번호" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" full loading={loading}>로그인</Button>
      </form>
      {/* 글자 링크도 누르는 칸은 44px */}
      <div className="mt-4 flex items-center justify-center gap-2 text-sm text-muted">
        <Link to="/password/forgot" className="flex min-h-11 items-center px-2 hover:text-ink-2">비밀번호 찾기</Link>
        <span className="text-faint" aria-hidden="true">|</span>
        <Link to="/signup" className="flex min-h-11 items-center px-2 font-semibold text-brand-ink">회원가입</Link>
      </div>
      <p className="text-center text-xs text-muted"><Link to="/help" className="inline-flex min-h-11 items-center px-2 underline underline-offset-2 hover:text-ink-2">도움말 · 문의</Link></p>
      </main>
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
      // 초대 링크로 왔으면 설문을 먼저 하고 그 링크로(설문이 끝날 때 꺼낸다 — 흐름 A). 아니면 홈 — 시작 안내 팝업에서 설문·팀 가입으로 안내
      nav(peekReturnTo() ? '/survey' : '/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.code === 'VALIDATION_ERROR') {
        const fe: Record<string, string> = {}
        err.details.forEach((d) => {
          if (d.field) fe[d.field.replace(/^body\./, '')] = d.reason
        })
        setFieldErrors(fe)
      }
      setError(errorMessage(err, '회원가입에 실패했어요.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Screen>
      <main className="flex flex-1 flex-col px-6 pb-8">
      <div className="pt-10 pb-6">
        <h1 className="text-2xl font-black text-ink">회원가입</h1>
        {/* 가입하면 홈으로 간다 — 홈의 시작 안내(팝업 → 할 일 목록)가 팀 가입 · 2분짜리 실력 설문을 차례로 안내한다 */}
        <p className="mt-1 text-sm text-muted">가입하면 홈에서 시작 안내가 떠요. 팀 가입과 2분짜리 실력 설문을 차례로 도와드려요.</p>
      </div>
      {/* 주 경로는 카카오 — 로그인 화면과 같은 버튼 */}
      <KakaoButton />
      <div className="my-5 flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-line" />또는 이메일로 가입<span className="h-px flex-1 bg-line" />
      </div>
      <form onSubmit={submit} className="space-y-3">
        <Field label="이메일" type="email" autoComplete="email" value={form.email} onChange={set('email')} error={fieldErrors.email} required />
        <Field label="비밀번호" type="password" autoComplete="new-password" minLength={8} value={form.password} onChange={set('password')} hint="8자 이상" error={fieldErrors.password} required />
        <Field label="이름" autoComplete="name" value={form.name} onChange={set('name')} error={fieldErrors.name} required />
        <Field label="닉네임 (선택)" autoComplete="nickname" value={form.nickname} onChange={set('nickname')} hint="팀원에게 보이는 이름이에요. 비우면 이름을 써요." />
        <Field label="키 (cm)" type="text" inputMode="numeric" value={form.height_cm} onChange={(e) => setForm({ ...form, height_cm: e.target.value.replace(/\D/g, '').slice(0, 3) })} placeholder="178" hint="골밑 적성 계산에만 쓰이고 다른 팀원에게 보이지 않아요." error={fieldErrors.height_cm} />
        {error && <Alert>{error}</Alert>}
        <Button type="submit" full loading={loading} className="mt-2">가입하기</Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted">
        이미 계정이 있나요? <Link to="/login" className="inline-flex min-h-11 items-center px-1 font-semibold text-brand-ink">로그인</Link>
      </p>
      </main>
    </Screen>
  )
}
