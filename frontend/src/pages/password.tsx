/**
 * 비밀번호 찾기(/password/forgot) · 재설정(/password/reset?token=) — FR-02.
 * 찾기는 계정 유무와 무관하게 항상 "메일을 보냈어요"를 보여준다 (서버가 항상 202를 주는 것과 같은 이유).
 */
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { authApi } from '../api/auth'
import { Alert, Button, Field } from '../components/ui'
import { Screen, TopBar } from '../components/layout'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null); setLoading(true)
    try { await authApi.forgotPassword(email.trim()); setSent(true) } catch (err) { setError(err instanceof ApiError ? err.message : '요청을 보내지 못했어요.') } finally { setLoading(false) }
  }
  return (
    <Screen className="px-6">
      <TopBar title="비밀번호 찾기" back="/login" />
      {sent ? (
        <div className="space-y-4 pt-6">
          <Alert kind="info">가입된 이메일이면 재설정 링크를 보냈어요. 30분 안에 메일의 링크를 열어 주세요. 메일이 없으면 스팸함을 확인해 주세요.</Alert>
          <Link to="/login"><Button full variant="secondary">로그인 화면으로</Button></Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3 pt-6">
          <p className="text-sm text-muted">가입한 이메일을 입력하면 비밀번호를 새로 정할 수 있는 링크를 보내 드려요. 카카오로 가입했다면 카카오 로그인을 이용해 주세요.</p>
          <Field label="이메일" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required autoFocus />
          {error && <Alert>{error}</Alert>}
          <Button type="submit" full loading={loading} disabled={!email.trim()}>재설정 링크 보내기</Button>
        </form>
      )}
    </Screen>
  )
}

export function ResetPasswordPage() {
  const nav = useNavigate()
  const token = new URLSearchParams(window.location.search).get('token') ?? ''
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)  // 링크가 만료·재사용된 경우에만 '링크 다시 받기'를 붙인다
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const mismatch = pw2.length > 0 && pw !== pw2
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (pw !== pw2) return
    setError(null); setLoading(true)
    try {
      await authApi.resetPassword(token, pw)
      setDone(true)
    } catch (err) {
      // 문구가 아니라 코드로 판단한다 — 안내 문구를 고쳐도 분기가 조용히 깨지지 않게
      setExpired(err instanceof ApiError && err.code === 'TOKEN_INVALID_OR_EXPIRED')
      setError(err instanceof ApiError ? err.message : '비밀번호를 바꾸지 못했어요.')
    } finally { setLoading(false) }
  }
  if (!token) {
    return (
      <Screen className="px-6">
        <TopBar title="비밀번호 재설정" back="/login" />
        <div className="space-y-4 pt-6"><Alert>재설정 링크가 올바르지 않아요. 메일의 링크를 다시 열어 주세요.</Alert><Link to="/password/forgot"><Button full variant="secondary">링크 다시 받기</Button></Link></div>
      </Screen>
    )
  }
  return (
    <Screen className="px-6">
      <TopBar title="비밀번호 재설정" back="/login" />
      {done ? (
        <div className="space-y-4 pt-6">
          <Alert kind="info">비밀번호를 바꿨어요. 새 비밀번호로 로그인해 주세요.</Alert>
          <Button full onClick={() => nav('/login', { replace: true })}>로그인하러 가기</Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3 pt-6">
          <Field label="새 비밀번호" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} hint="8자 이상" minLength={8} required autoFocus />
          <Field label="새 비밀번호 확인" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} error={mismatch ? '비밀번호가 서로 달라요.' : undefined} required />
          {error && <Alert>{error}{expired ? <> <Link to="/password/forgot" className="font-semibold underline">링크 다시 받기</Link></> : null}</Alert>}
          <Button type="submit" full loading={loading} disabled={pw.length < 8 || mismatch}>비밀번호 바꾸기</Button>
        </form>
      )}
    </Screen>
  )
}
