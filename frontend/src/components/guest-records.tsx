/**
 * S-08 팀원 관리의 게스트 기록 잇기 (FR-13, docs/09 3-4 · 3-5).
 * - 같은 이름의 짝: 기록 이어 주기 / "다른 사람이에요" 로 숨기기 (그 회원의 본인 확인 카드도 사라진다)
 * - 이어 준 기록: 매니저가 이었든 본인 확인으로 이었든 여기서 되돌린다
 * - 이름이 다른 게스트: 게스트를 찾아 팀원을 골라 잇는다 (게스트 때 "민수" · 가입 뒤 "김민수")
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { errorMessage as errMsg } from '../api/client'
import { teamsApi } from '../api/teams'
import type { PlayerCard } from '../api/types'
import { confirm, toast } from '../store/feedback'
import { Alert, Button, Card, Field, SectionTitle, Sheet, Spinner } from './ui'

export function GuestRecordsSection({ teamId, members }: { teamId: number; members: PlayerCard[] }) {
  const qc = useQueryClient()
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['team', teamId] })  // players · merge-candidates · merged
    qc.invalidateQueries({ queryKey: ['stats'] })
  }
  const candidates = useQuery({ queryKey: ['team', teamId, 'merge-candidates'], queryFn: () => teamsApi.mergeCandidates(teamId) })
  const merged = useQuery({ queryKey: ['team', teamId, 'merged-guests'], queryFn: () => teamsApi.mergedGuests(teamId) })
  const [picking, setPicking] = useState(false)

  const merge = useMutation({
    mutationFn: ({ guest, into }: { guest: number; into: number }) => teamsApi.mergeGuest(guest, into),
    onSuccess: () => { toast('기록을 이어 줬어요.'); setPicking(false); refresh() },
    onError: (e) => toast(errMsg(e, '기록을 이어 주지 못했어요.'), 'error'),
  })
  const dismiss = useMutation({
    mutationFn: ({ guest, member }: { guest: number; member: number }) => teamsApi.dismissMergeCandidate(teamId, guest, member),
    onSuccess: () => { toast('다른 사람으로 표시했어요.'); refresh() },
    onError: (e) => toast(errMsg(e, '표시하지 못했어요.'), 'error'),
  })
  const unmerge = useMutation({
    mutationFn: (guest: number) => teamsApi.unmergeGuest(guest),
    onSuccess: () => { toast('되돌렸어요. 게스트 기록이 따로 남아요.'); refresh() },
    onError: (e) => toast(errMsg(e, '되돌리지 못했어요.'), 'error'),
  })
  const askMerge = async (guest: PlayerCard, member: PlayerCard) => {
    if (await confirm({ title: '게스트 기록을 이어 줄까요?', body: `게스트 ${guest.display_name}의 배정 · 경기 · 투표 기록이 ${member.display_name}님 기록으로 이어져요. 아래 "이어 준 기록"에서 되돌릴 수 있어요.`, confirmLabel: '기록 이어 주기' })) merge.mutate({ guest: guest.id, into: member.id })
  }

  const cands = candidates.data?.items ?? []
  const done = merged.data?.items ?? []
  return (
    <section>
      <SectionTitle action={
        <button className="-my-2 min-h-11 px-1 text-xs font-semibold text-brand-ink" onClick={() => setPicking(true)}>다른 이름으로 잇기</button>
      }>게스트 기록 잇기</SectionTitle>
      {cands.length === 0 && done.length === 0 && (
        <p className="px-1 text-xs text-muted">게스트로 오던 사람이 가입하면 같은 이름끼리 여기에 떠요. 이름이 다르면 "다른 이름으로 잇기"로 이어 주세요.</p>
      )}
      {cands.length > 0 && (
        <>
          <Alert kind="info">같은 이름의 게스트 기록이 있어요. 같은 사람이면 이어 주고, 이름만 같은 다른 사람이면 "다른 사람"을 눌러 주세요.</Alert>
          <div className="mt-2 space-y-2">
            {cands.map((c) => (
              <Card key={`${c.guest.id}-${c.member.id}`} className="space-y-2 py-3">
                <div className="text-sm">
                  <p className="font-semibold text-ink">게스트 {c.guest.display_name} <span className="text-faint">→</span> 팀원 {c.member.display_name}</p>
                  <p className="text-xs text-muted">게스트 때 배정 · 경기 · 투표 기록이 이 팀원 기록으로 이어져요.</p>
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="ghost" className="text-sm" disabled={dismiss.isPending || merge.isPending}
                    loading={dismiss.isPending && dismiss.variables?.guest === c.guest.id && dismiss.variables?.member === c.member.id}
                    onClick={() => dismiss.mutate({ guest: c.guest.id, member: c.member.id })}
                  >
                    다른 사람
                  </Button>
                  <Button
                    className="text-sm" disabled={merge.isPending || dismiss.isPending}
                    loading={merge.isPending && merge.variables?.guest === c.guest.id}
                    onClick={() => askMerge(c.guest, c.member)}
                  >
                    기록 이어 주기
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
      {done.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 px-1 text-xs font-semibold text-muted">이어 준 기록</p>
          <div className="space-y-2">
            {done.map((c) => (
              <Card key={c.guest.id} className="flex items-center gap-3 py-3">
                <p className="min-w-0 flex-1 text-sm text-ink">게스트 {c.guest.display_name} <span className="text-faint">→</span> {c.member.display_name}</p>
                <Button
                  variant="ghost" className="shrink-0 text-sm" disabled={unmerge.isPending}
                  loading={unmerge.isPending && unmerge.variables === c.guest.id}
                  onClick={async () => { if (await confirm({ title: '이어 준 기록을 되돌릴까요?', body: `게스트 ${c.guest.display_name}의 기록이 ${c.member.display_name}님 기록에서 빠져 다시 게스트 기록으로 남아요. 실력 지표도 다시 계산해요.`, confirmLabel: '되돌리기', danger: true })) unmerge.mutate(c.guest.id) }}
                >
                  되돌리기
                </Button>
              </Card>
            ))}
          </div>
        </div>
      )}
      {picking && <PickMergeSheet teamId={teamId} members={members} busy={merge.isPending} onPick={askMerge} onClose={() => setPicking(false)} />}
    </section>
  )
}

/** 이름이 다른 게스트 → 팀원. 게스트를 고르고 팀원을 고른다 */
function PickMergeSheet({ teamId, members, busy, onPick, onClose }: {
  teamId: number; members: PlayerCard[]; busy: boolean; onPick: (g: PlayerCard, m: PlayerCard) => void; onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [guest, setGuest] = useState<PlayerCard | null>(null)
  const guests = useQuery({ queryKey: ['team', teamId, 'guests-all'], queryFn: () => teamsApi.guests(teamId) })
  const term = q.trim().toLowerCase()
  const list = (guests.data?.items ?? []).filter((g) => !term || g.display_name.toLowerCase().includes(term)).slice(0, 30)
  return (
    <Sheet label="다른 이름으로 게스트 기록 잇기" title={guest ? `게스트 ${guest.display_name} → 누구에게 이을까요?` : '어느 게스트의 기록인가요?'} onClose={onClose}>
      {!guest ? (
        <div className="space-y-3">
          <Field label="게스트 이름" value={q} onChange={(e) => setQ(e.target.value)} placeholder="이름 일부로 찾기" />
          {guests.isLoading ? <Spinner /> : list.length === 0 ? (
            <p className="text-sm text-muted">{term ? '그 이름의 게스트가 없어요.' : '아직 이을 수 있는 게스트가 없어요.'}</p>
          ) : (
            <div className="space-y-1.5">
              {list.map((g) => (
                <button key={g.id} onClick={() => setGuest(g)} className="flex min-h-11 w-full items-center justify-between rounded-xl border border-line px-3 text-left text-sm">
                  <span className="font-semibold text-ink">{g.display_name}</span><span className="text-faint">→</span>
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          {members.map((m) => (
            <button key={m.id} disabled={busy} onClick={() => onPick(guest, m)} className="flex min-h-11 w-full items-center justify-between rounded-xl border border-line px-3 text-left text-sm disabled:opacity-50">
              <span className="font-semibold text-ink">{m.display_name}</span><span className="text-xs text-muted">이 팀원에게 잇기</span>
            </button>
          ))}
          <button className="mt-2 min-h-11 w-full text-sm font-semibold text-brand-ink" onClick={() => setGuest(null)}>← 게스트 다시 고르기</button>
        </div>
      )}
    </Sheet>
  )
}
