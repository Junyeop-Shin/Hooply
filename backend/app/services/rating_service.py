"""실력 지표 갱신 — 잔차 기반 실시간 Elo (설계서 9.1 ~ 9.2절 층 1 · F10).

왜 원시 마진을 누적하지 않는가 (9.1절): 쿼터 마진은 제로섬이고, 배정이 잘 될수록 0으로 수렴하며, 잘하는
사람일수록 약한 팀에 배정돼 마진이 낮게 나온다. 그래서 "실제 마진 − 기대 마진" 인 **잔차**만 반영한다.

쿼터 하나를 처리하는 식 (9.2절)
  1. M' = clip(실제 마진, −15, +15) × (10 / 쿼터 길이)      ← 블로우아웃·가비지타임 상한, 시간 정규화
  2. E  = Σ(블랙 출전 5명 r) − Σ(화이트 출전 5명 r)          ← 기대 마진
  3. D  = M' − E                                            ← 잔차
  4. r_i ← r_i ± K_i × D / 5   (블랙 +, 화이트 −)
  5. n_i ← n_i + 1,   K_i = 0.35 / (1 + n_i / 20)            ← 신규는 빠르게, 표본이 쌓이면 둔감하게

왜 매번 팀 전체를 처음부터 다시 계산하는가 (13.2절 2항): 쿼터 수가 유동적이라 삭제·수정이 실제로 일어난다.
증분으로만 갱신하면 롤백이 불가능하므로, 원본 라인업을 보존해 두고 저장·수정·삭제 때마다 팀의 모든
쿼터를 시간순으로 재생한다. 24명 × 300쿼터 규모는 밀리초 단위다.

첫 2회 모임 게이트 (13.2절 1항, Settings.rating_warmup_events): 팀에서 쿼터가 기록된 첫 두 회차는 마진만
저장하고 지표에는 넣지 않는다 (노이즈가 사전값을 악화시킨다).

게스트 → 회원 병합 (6.2절): 라인업의 player_id 가 병합된 게스트면 `merged_into_player_id` 를 따라 올라가
회원의 기록으로 합산한다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models import Event, Player, PlayerProfile, Quarter, QuarterLineup, SkillRatingHistory
from app.models.enums import EventStatus, PlayerKind, PriorSource, RatingSource, Side

K_BASE = 0.35  # 적응형 학습률의 시작값
K_DECAY_N = 20  # n 이 20 쌓이면 K 가 절반이 된다
MARGIN_CLIP = 15  # 쿼터 마진 상한 (9.2절 1단계)
REFERENCE_MIN = 10  # 10분 환산 기준
CONF_PER_QUARTER = 0.015  # 평가된 쿼터 1개당 신뢰도 증가분 (20쿼터 ≈ +0.3)
CONF_MAX = 0.95


def normalized_margin(raw: int, duration_min: int) -> Decimal:
    """raw_margin × (10 / duration_min). 저장용 (클리핑 없음)."""
    return Decimal(str(round(raw * REFERENCE_MIN / max(1, duration_min), 2)))


def _clipped_margin(raw: int, duration_min: int) -> float:
    """10분 환산한 뒤 상한을 건다. 짧은 쿼터일수록 정규화 배수가 커지므로 환산 전에 자르면 상한이 무의미해진다
    (1분 쿼터에서 15점 차 → 150점). 10분 쿼터에서는 예전과 같은 값이다."""
    return max(-MARGIN_CLIP, min(MARGIN_CLIP, raw * REFERENCE_MIN / max(1, duration_min)))


def _base_confidence(prof: PlayerProfile, kind: PlayerKind) -> float:
    """쿼터가 하나도 없을 때의 신뢰도 — 사전값 출처에 따라 (survey_service / guest_service 와 같은 값)."""
    if prof.prior_source == PriorSource.SURVEY:
        return 0.40
    if prof.prior_source == PriorSource.MANAGER:
        return 0.25 if kind == PlayerKind.GUEST else 0.30
    return 0.0


def recompute_team(db: Session, team_id: int) -> dict[str, int]:
    """팀의 모든 쿼터를 시간순으로 재생해 skill_overall·quarters_played·cumulative_residual·신뢰도를 다시 쓴다.

    부수 효과: player_profiles UPDATE, 값이 바뀐 사람마다 skill_rating_history(source=RESIDUAL). flush 까지.
    반환: {"quarters": 전체 쿼터 수, "rated": 지표에 반영된 쿼터 수, "warmup_events": 게이트로 제외된 회차 수}
    """
    settings = get_settings()
    players = db.scalars(
        select(Player).where(Player.team_id == team_id).options(selectinload(Player.profile))
    ).all()
    by_id = {p.id: p for p in players}

    def canonical(pid: int) -> int:
        """병합된 게스트는 회원 행으로 (포인터 체인 따라가기, 순환 방지)."""
        seen = set()
        while pid in by_id and by_id[pid].merged_into_player_id and pid not in seen:
            seen.add(pid)
            pid = by_id[pid].merged_into_player_id
        return pid

    r: dict[int, float] = {}
    for p in players:
        prof = p.profile
        r[p.id] = float(prof.prior_overall) if prof and prof.prior_overall is not None else 0.0
    n_rated: dict[int, int] = defaultdict(int)
    n_played: dict[int, int] = defaultdict(int)
    residual: dict[int, float] = defaultdict(float)
    margins: dict[int, list[float]] = defaultdict(list)

    # 팀의 모든 쿼터를 다시 재생하므로 행 수가 누적 쿼터 × 10 이다. ORM 객체를 만들지 않고 필요한 값만
    # 튜플로 받는다 — 여기 비용의 대부분이 객체 생성이라, 같은 결과를 훨씬 싸게 얻는다.
    rows = db.execute(
        select(
            Quarter.id, Quarter.event_id, Quarter.black_score, Quarter.white_score, Quarter.duration_min,
            QuarterLineup.player_id, QuarterLineup.side, QuarterLineup.normalized_margin,
        )
        .join(Event, Event.id == Quarter.event_id)
        .join(QuarterLineup, QuarterLineup.quarter_id == Quarter.id)
        .where(Event.team_id == team_id, Event.status != EventStatus.CANCELED)
        .order_by(Event.event_date, Event.start_time.nulls_first(), Event.id, Quarter.quarter_no)
    ).all()

    @dataclass(slots=True)
    class _Q:
        event_id: int
        black_score: int
        white_score: int
        duration_min: int
        lineups: list[tuple[int, Side, float]]  # (player_id, side, normalized_margin)

    quarters: list[_Q] = []
    seen_q: dict[int, _Q] = {}
    for qid, eid, bs, ws, dur, pid_, side_, nm in rows:
        q = seen_q.get(qid)
        if q is None:
            q = _Q(event_id=eid, black_score=bs, white_score=ws, duration_min=dur, lineups=[])
            seen_q[qid] = q
            quarters.append(q)
        q.lineups.append((pid_, side_, float(nm)))

    event_order: list[int] = []
    for q in quarters:
        if q.event_id not in event_order:
            event_order.append(q.event_id)
    warmup = set(event_order[: settings.rating_warmup_events])

    rated = 0
    for q in quarters:
        black = [canonical(pid_) for pid_, side_, _ in q.lineups if side_ == Side.BLACK]
        white = [canonical(pid_) for pid_, side_, _ in q.lineups if side_ == Side.WHITE]
        for pid_, _side, nm in q.lineups:
            c = canonical(pid_)
            n_played[c] += 1
            margins[c].append(nm)
        if q.event_id in warmup:
            continue  # 첫 2회 모임: 마진은 기록하되 지표에는 넣지 않는다
        rated += 1
        m = _clipped_margin(q.black_score - q.white_score, q.duration_min)
        expected = sum(r.get(p, 0.0) for p in black) - sum(r.get(p, 0.0) for p in white)
        d = m - expected
        for pid, sign in [(p, +1) for p in black] + [(p, -1) for p in white]:
            k = K_BASE / (1 + n_rated[pid] / K_DECAY_N)
            r[pid] = r.get(pid, 0.0) + sign * k * d / 5
            n_rated[pid] += 1
            residual[pid] += sign * d

    for p in players:
        prof = p.profile
        if prof is None or p.merged_into_player_id:  # 병합된 게스트의 기록은 회원 쪽에 합산됐다
            continue
        before = prof.skill_overall
        # 사전값도 없고 평가 쿼터도 없으면 "모름"(None) 을 유지한다 — 0.0 을 쓰면 클럽 평균으로 오독된다
        after = None if (prof.prior_overall is None and n_rated[p.id] == 0) else Decimal(str(round(r[p.id], 1)))
        prof.skill_overall = after
        prof.quarters_played = n_played[p.id]
        prof.cumulative_residual = Decimal(str(round(residual[p.id], 2)))
        prof.avg_margin_per_quarter = Decimal(str(round(mean(margins[p.id]), 2))) if margins[p.id] else None
        if n_rated[p.id] > 0:
            # 평가 쿼터가 있을 때만 신뢰도를 다시 쓴다. 없으면 설문/게스트 서비스가 정한 기준값을 그대로 둔다.
            # 현재 값이 아니라 기준값에서 다시 계산해야 쿼터 삭제 시 롤백이 정확히 맞는다 (13.2절 2항)
            conf = min(CONF_MAX, _base_confidence(prof, p.kind) + CONF_PER_QUARTER * n_rated[p.id])
            prof.skill_confidence = Decimal(str(round(conf, 2)))
        if before != after and n_rated[p.id] > 0:
            db.add(
                SkillRatingHistory(
                    player_id=p.id, source=RatingSource.RESIDUAL, before_value=before, after_value=after,
                    delta=after - (before or Decimal(0)), ref_type="team_recompute", ref_id=team_id,
                    reason=f"경기 기록 반영 (쿼터 {n_rated[p.id]}개)",
                )
            )
    db.flush()
    return {"quarters": len(quarters), "rated": rated, "warmup_events": len(warmup)}
