/**
 * 도움말 · 문의 — 로그인 없이도 열린다 (연락이 가장 필요한 때가 로그인이 안 될 때라서).
 * 들어오는 곳: 내 프로필 "도움말 · 문의", 로그인 화면 아래 링크. 문장은 lib/help-content.ts 한 곳에서 관리한다.
 */
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { tutorialApi } from '../api/tutorial'
import { useIsLoggedIn } from '../store/auth'
import { CONTACT_EMAIL, HELP_SECTIONS } from '../lib/help-content'
import { Badge, Button, Card, SectionTitle } from '../components/ui'
import { Content, Screen, TopBar } from '../components/layout'

export function HelpPage() {
  const loggedIn = useIsLoggedIn()
  const { hash } = useLocation()
  const target = hash.replace('#', '')
  // 프로필을 내려 둔 채 들어오면 스크롤 위치가 그대로 남아 맨 아래부터 보인다. 맨 위로 — 주제를 지정해 왔으면 그 주제로
  useEffect(() => {
    const el = target ? document.getElementById(target) : null
    if (el) el.scrollIntoView({ block: 'start' })
    else window.scrollTo(0, 0)
  }, [target])
  return (
    <Screen>
      <TopBar title="도움말" back={loggedIn ? '/me' : '/login'} />
      <Content>
        <p className="px-1 text-sm text-muted">궁금한 주제를 눌러 펼쳐 보세요. <span className="whitespace-nowrap">매니저 표시가 있는 주제는 매니저만 쓰는 기능이에요.</span></p>
        {loggedIn && <RestartTutorial />}
        <div className="space-y-2">
          {HELP_SECTIONS.map((s, i) => (
            <details key={s.id} id={s.id} open={target ? target === s.id : i === 0} className="group rounded-2xl border border-line bg-surface">
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-2 px-4 py-3 [&::-webkit-details-marker]:hidden">
                <span className="flex-1 font-semibold text-ink">{s.title}</span>
                {s.manager && <Badge tone="navy">매니저</Badge>}
                <span className="text-faint transition-transform group-open:rotate-180" aria-hidden="true">▾</span>
              </summary>
              <div className="space-y-4 border-t border-line px-4 pb-4 pt-3">
                {s.items.map((it) => (
                  <div key={it.q}>
                    <p className="text-sm font-bold text-ink">{it.q}</p>
                    <div className="mt-1 space-y-1.5">
                      {it.a.map((line) => <p key={line} className="text-sm leading-relaxed text-ink-2">{line}</p>)}
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
        <ContactCard />
      </Content>
    </Screen>
  )
}

/** 시작 안내를 거절했거나 닫았던 사람이 다시 켠다 (경로 선택부터) */
function RestartTutorial() {
  const me = useQuery({ queryKey: ['me'], queryFn: authApi.me })
  const qc = useQueryClient()
  const nav = useNavigate()
  const restart = useMutation({
    mutationFn: () => tutorialApi.update({ state: 'ACTIVE' }),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ['me'] }); nav('/') },
  })
  if (!me.data || me.data.tutorial_state === 'ACTIVE') return null
  return (
    <Card className="flex items-center justify-between gap-3">
      <div><p className="text-sm font-semibold text-ink">시작 안내 다시 보기</p><p className="text-xs text-muted">홈에 할 일 목록이 다시 생기고, 기능별 첫 안내도 켜져요.</p></div>
      <Button variant="ghost" className="min-h-10 shrink-0 text-sm" loading={restart.isPending} onClick={() => restart.mutate()}>다시 보기</Button>
    </Card>
  )
}

function ContactCard() {
  const [copied, setCopied] = useState<'ok' | 'fail' | null>(null)
  const copy = async () => {
    try { await navigator.clipboard.writeText(CONTACT_EMAIL); setCopied('ok') } catch { setCopied('fail') }
  }
  return (
    <section>
      <SectionTitle>문의</SectionTitle>
      <Card className="space-y-3">
        <p className="text-sm text-ink-2">오류가 있거나 궁금한 점이 풀리지 않으면 개발자에게 메일을 보내 주세요.</p>
        <div className="flex items-center gap-2 rounded-xl bg-surface-2 px-3 py-2.5">
          <span className="flex-1 select-all break-all font-semibold text-ink">{CONTACT_EMAIL}</span>
          <button type="button" onClick={copy} className="min-h-9 shrink-0 rounded-lg border border-line bg-surface px-3 text-sm font-semibold text-ink-2 active:bg-sunken">복사</button>
          <a href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('[Hooply 문의] ')}`} className="flex min-h-9 shrink-0 items-center rounded-lg bg-brand px-3 text-sm font-semibold text-on-brand">메일 쓰기</a>
        </div>
        {copied === 'ok' && <p className="text-xs text-ok-ink">주소를 복사했어요.</p>}
        {copied === 'fail' && <p className="text-xs text-muted">복사하지 못했어요. 주소를 길게 눌러 복사해 주세요.</p>}
        <div className="text-xs text-muted">
          <p className="font-semibold text-ink-2">보낼 때 알려 주시면 빨리 도와드릴 수 있어요</p>
          <p>팀 이름 · 쓰는 기기(아이폰/안드로이드, 카카오톡 안에서 열었는지) · 문제가 생긴 화면 캡처</p>
        </div>
        <p className="text-[11px] text-faint">카카오톡 안에서 열었다면 "메일 쓰기"가 동작하지 않을 수 있어요. 그때는 주소를 복사해 메일 앱에 붙여 넣어 주세요.</p>
      </Card>
    </section>
  )
}
