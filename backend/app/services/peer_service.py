"""피어 투표 서비스 (설계서 F9 · F10 · 9.4절 · peer-vote-spec).

원칙 (9.4절): 케미는 코트 마진으로 *측정* 하지 않고 경기 후 투표로 *선언* 받는다.
스펙(재설계)에서 바뀐 것
  - 카테고리당 0~2명 (상한만, 하한 없음). 억지 2번째 선택의 잡음을 없앤다.
  - 후보는 그날 참석자 전원(본인 제외, 게스트 포함) 한 리스트. 같은 팀/상대 팀은 배지로만 구분.
  - "또 뛰고 싶은 사람" 에는 이유 태그 1개(선택). "잘한 사람" 은 **표시 전용** — 실력 산출에 넣지 않는다.
  - 오픈 시점: 일정 종료 시각(event_date + end_time)이 지나면 자동. 쿼터 기록 여부와 무관.
  - 독려: 시스템 자동 발송 없음. 매니저가 카카오톡 단체방에 공유할 메시지만 만들어 준다.
  - pref_score: 함께 참석한 회차 수 대비 지목 비율 + 최근 회차 가중 (0.9^k), 0~1 클립. 투표 제출마다 팀 단위로 재계산.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import errors
from app.core.config import get_settings
from app.models import (
    AssignmentCandidate,
    AssignmentRun,
    AssignmentSlot,
    AssignmentSquad,
    ChemistryScore,
    Event,
    EventAttendance,
    Player,
    PlayerProfile,
    PostGameSurvey,
    PostGameVote,
    QuarterLineup,
)
from app.models.enums import (
    AttendanceStatus,
    EventStatus,
    PlayerKind,
    PlayerStatus,
    TargetSide,
    VoteType,
)
from app.schemas.peer import (
    CompatiblePlayer,
    PlayerStats,
    PostGameSurveyIn,
    ShareMessage,
    VoteCandidate,
    VoteTargets,
    VoteView,
)
from app.services.player_service import to_card

MAX_PER_SIDE = 2  # 같은 팀 최대 2명 + 상대 팀 최대 2명 (사용자 결정). 확정 배정이 없던 회차는 합계 4명까지
DECAY = 0.9  # 최근 가중 감쇠율 — 약 7회 전 투표는 절반 가중치 (스펙 4.1절)
BEST_WINDOW_DAYS = 90  # peer_vote_score(표시 전용) 집계 기간


# ---------------------------------------------------------------------------
# 오픈 여부 · 진행 현황
# ---------------------------------------------------------------------------


def opens_at(event: Event) -> datetime:
    """투표가 열리는 시각 = 일정 종료 시각 (end_time 없으면 그날 자정). 서비스 시간대(settings.timezone) 기준.

    컨테이너 로컬 시간대(보통 UTC)로 해석하면 한국 12:00 종료가 21:00 에 열리는 버그가 생기므로 명시적으로 변환한다.
    """
    t = event.end_time or time(23, 59)
    return datetime.combine(event.event_date, t, tzinfo=ZoneInfo(get_settings().timezone))


def is_open(event: Event) -> bool:
    if event.status == EventStatus.CANCELED:
        return False
    return datetime.now(UTC) >= opens_at(event)


def _attending_players(db: Session, event: Event) -> list[Player]:
    return list(
        db.scalars(
            select(Player)
            .join(EventAttendance, EventAttendance.player_id == Player.id)
            .where(EventAttendance.event_id == event.id, EventAttendance.status == AttendanceStatus.ATTEND)
            .options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))
            .order_by(Player.display_name)
        ).all()
    )


def progress(db: Session, event: Event) -> tuple[int, int]:
    """(제출 수, 대상 인원). 대상 = 참석한 회원(게스트 제외)."""
    total = db.scalar(
        select(func.count()).select_from(EventAttendance).join(Player, Player.id == EventAttendance.player_id)
        .where(EventAttendance.event_id == event.id, EventAttendance.status == AttendanceStatus.ATTEND, Player.kind == PlayerKind.MEMBER)
    ) or 0
    responded = db.scalar(select(func.count()).select_from(PostGameSurvey).where(PostGameSurvey.event_id == event.id)) or 0
    return responded, total


def my_survey(db: Session, event: Event, player_id: int) -> PostGameSurvey | None:
    return db.scalar(
        select(PostGameSurvey).where(PostGameSurvey.event_id == event.id, PostGameSurvey.respondent_player_id == player_id)
        .options(selectinload(PostGameSurvey.votes))
    )


def _squad_of(db: Session, event: Event) -> dict[int, tuple[int, str]]:
    """확정 배정의 player_id → (squad_no, squad_name). 없으면 빈 dict."""
    rows = db.execute(
        select(AssignmentSlot.player_id, AssignmentSquad.squad_no, AssignmentSquad.squad_name)
        .join(AssignmentSquad, AssignmentSquad.id == AssignmentSlot.squad_id)
        .join(AssignmentCandidate, AssignmentCandidate.id == AssignmentSquad.candidate_id)
        .join(AssignmentRun, AssignmentRun.id == AssignmentCandidate.run_id)
        .where(AssignmentRun.event_id == event.id, AssignmentCandidate.is_adopted.is_(True))
    ).all()
    return {pid: (no, name) for pid, no, name in rows}


# ---------------------------------------------------------------------------
# 후보 · 제출
# ---------------------------------------------------------------------------


def _require_respondent(db: Session, event: Event, me: Player) -> Player:
    """응답자는 그 회차 참석(ATTEND)한 회원이어야 한다."""
    row = db.scalar(
        select(EventAttendance).where(EventAttendance.event_id == event.id, EventAttendance.player_id == me.id, EventAttendance.status == AttendanceStatus.ATTEND)
    )
    player = db.get(Player, me.id) if me.id else None
    if row is None or player is None or player.kind != PlayerKind.MEMBER:
        raise errors.NotAttendee()
    return player


def targets(db: Session, event: Event, me: Player) -> VoteTargets:
    """후보 명단 + 내 상태. 종료 전이면 403 SURVEY_NOT_OPEN (프론트는 안내 문구만 보여준다)."""
    respondent = _require_respondent(db, event, me)
    if not is_open(event):
        raise errors.SurveyNotOpen(details=[])
    squads = _squad_of(db, event)
    my_squad = squads.get(respondent.id)
    candidates = []
    for p in _attending_players(db, event):
        if p.id == respondent.id:
            continue
        sq = squads.get(p.id)
        candidates.append(
            VoteCandidate(
                player=to_card(p), squad_no=sq[0] if sq else None, squad_name=sq[1] if sq else None,
                is_same_team=(sq is not None and my_squad is not None and sq[0] == my_squad[0]) if sq and my_squad else None,
            )
        )
    mine = my_survey(db, event, respondent.id)
    return VoteTargets(
        open=True, opens_at=opens_at(event), already_submitted=mine is not None,
        my_votes=[VoteView(target_player_id=v.target_player_id, vote_type=v.vote_type, reason_tag=v.reason_tag) for v in (mine.votes if mine else [])],
        candidates=candidates,
    )


def submit(db: Session, event: Event, me: Player, body: PostGameSurveyIn) -> PostGameSurvey:
    respondent = _require_respondent(db, event, me)
    if not is_open(event):
        raise errors.SurveyNotOpen()
    if my_survey(db, event, respondent.id) is not None:
        raise errors.AlreadySubmitted("이미 이 회차 투표를 제출했어요.")
    attendee_ids = {p.id for p in _attending_players(db, event)}
    squads = _squad_of(db, event)
    my_squad = squads.get(respondent.id)

    def side_of(pid: int) -> TargetSide | None:
        sq = squads.get(pid)
        if sq and my_squad:
            return TargetSide.SAME_TEAM if sq[0] == my_squad[0] else TargetSide.OPPONENT
        return None  # 확정 배정이 없던 회차

    seen: set[int] = set()
    per_side: dict[TargetSide | None, int] = defaultdict(int)
    for v in body.votes:
        if v.vote_type != VoteType.PLAY_AGAIN:
            raise errors.ValidationError("'다음에 같이 뛰고 싶은 사람' 투표만 받아요.")
        if v.target_player_id == respondent.id:
            raise errors.SelfVoteNotAllowed()
        if v.target_player_id not in attendee_ids:
            raise errors.ValidationError("그날 참석자만 고를 수 있어요.")
        if v.target_player_id in seen:
            raise errors.ValidationError("같은 사람을 두 번 고를 수 없어요.")
        seen.add(v.target_player_id)
        per_side[side_of(v.target_player_id)] += 1
    for side, n in per_side.items():
        if side is None and n > 2 * MAX_PER_SIDE:
            raise errors.ValidationError(f"최대 {2 * MAX_PER_SIDE}명까지 고를 수 있어요.")
        if side is not None and n > MAX_PER_SIDE:
            raise errors.ValidationError(f"{'같은 팀' if side == TargetSide.SAME_TEAM else '상대 팀'}에서는 최대 {MAX_PER_SIDE}명까지 고를 수 있어요.")
    survey = PostGameSurvey(event_id=event.id, respondent_player_id=respondent.id, submitted_at=datetime.now(UTC))
    for v in body.votes:
        survey.votes.append(PostGameVote(target_player_id=v.target_player_id, vote_type=v.vote_type, target_side=side_of(v.target_player_id), reason_tag=v.reason_tag))
    db.add(survey)
    db.flush()
    recompute_team_chemistry(db, event.team_id)
    db.commit()
    return survey


def share_message(db: Session, event: Event) -> ShareMessage:
    responded, total = progress(db, event)
    link = f"{get_settings().frontend_base_url.rstrip('/')}/events/{event.id}/vote"
    text = f"🏀 오늘 경기 어떠셨나요?\n같이 뛰고 싶은 사람에게 투표해주세요 (30초)\n👉 {link}"
    return ShareMessage(text=text, link=link, responded=responded, total=total, open=is_open(event), opens_at=opens_at(event))


# ---------------------------------------------------------------------------
# 집계: chemistry_scores (pref_*) · peer_vote_score (표시 전용)
# ---------------------------------------------------------------------------


def recompute_team_chemistry(db: Session, team_id: int) -> int:
    """팀의 PLAY_AGAIN 투표를 페어 단위로 집계해 chemistry_scores.pref_* 와 together_events 를 다시 쓴다.

    스펙 4.1절: 두 사람이 함께 참석한 회차를 최신순으로 나열해 k번째(0부터) 회차에서 지목했으면 0.9^k 를 더하고,
    함께 참석한 회차 수로 나눠 0~1 로 클립. 양방향(a→b, b→a) 평균이 pref_score, 둘 다 한 번이라도 지목했으면 mutual.
    BEST_PERFORMER 는 여기에 들어가지 않는다 (표시 전용, 4.2절). flush 까지.
    """
    events = db.scalars(
        select(Event).where(Event.team_id == team_id, Event.status != EventStatus.CANCELED).order_by(Event.event_date.desc(), Event.id.desc())
    ).all()
    event_ids = [e.id for e in events]
    if not event_ids:
        return 0
    att_rows = db.execute(
        select(EventAttendance.event_id, EventAttendance.player_id).where(EventAttendance.event_id.in_(event_ids), EventAttendance.status == AttendanceStatus.ATTEND)
    ).all()
    attend: dict[int, set[int]] = defaultdict(set)  # event_id → player_ids
    for eid, pid in att_rows:
        attend[eid].add(pid)
    vote_rows = db.execute(
        select(PostGameSurvey.event_id, PostGameSurvey.respondent_player_id, PostGameVote.target_player_id)
        .join(PostGameVote, PostGameVote.survey_id == PostGameSurvey.id)
        .where(PostGameSurvey.event_id.in_(event_ids), PostGameVote.vote_type == VoteType.PLAY_AGAIN)
    ).all()
    voted: dict[tuple[int, int], set[int]] = defaultdict(set)  # (from, to) → event_ids
    for eid, frm, to in vote_rows:
        voted[(frm, to)].add(eid)

    # 지목이 한 번이라도 있는 방향 쌍만 계산 (그 외 페어는 행을 만들지 않는다 — "케미 0점" 오독 방지)
    pairs = {tuple(sorted(k)) for k in voted}
    existing = {(c.player_a_id, c.player_b_id): c for c in db.scalars(select(ChemistryScore).where(ChemistryScore.player_a_id.in_([a for a, _ in pairs] or [-1]))).all()}
    kept = set()
    for a, b in pairs:
        common = [eid for eid in event_ids if a in attend[eid] and b in attend[eid]]  # 최신순
        together = len(common)
        p_ab = _directional_pref(common, voted.get((a, b), set()))
        p_ba = _directional_pref(common, voted.get((b, a), set()))
        row = existing.get((a, b))
        if row is None:
            row = ChemistryScore(player_a_id=a, player_b_id=b)
            db.add(row)
        row.together_events = together
        row.pref_score = Decimal(str(round((p_ab + p_ba) / 2, 2)))
        row.pref_mutual = bool(voted.get((a, b))) and bool(voted.get((b, a)))
        kept.add((a, b))
    # 투표가 모두 사라진 페어의 pref 는 비운다 (synergy 필드는 그대로)
    for key, row in existing.items():
        if key not in kept:
            row.pref_score = None
            row.pref_mutual = False
    _recompute_best_scores(db, team_id, event_ids)
    db.flush()
    return len(pairs)


def _directional_pref(common_events_desc: list[int], voted_events: set[int]) -> float:
    """한 방향(from→to) 선호 비율. 최신순 k번째 회차 지목에 0.9^k 가중, 함께 참석 회차 수로 나눠 0~1 클립 (스펙 4.1절)."""
    s = sum(DECAY**k for k, eid in enumerate(common_events_desc) if eid in voted_events)
    return min(1.0, s / max(len(common_events_desc), 1))


def _recompute_best_scores(db: Session, team_id: int, event_ids: list[int]) -> None:
    """player_profiles.peer_vote_score = 최근 90일 BEST_PERFORMER 지목 수. **표시 전용** — 실력 산출에 쓰지 않는다."""
    since = datetime.now(ZoneInfo(get_settings().timezone)).date().toordinal() - BEST_WINDOW_DAYS
    recent = [e.id for e in db.scalars(select(Event).where(Event.id.in_(event_ids))).all() if e.event_date.toordinal() >= since]
    counts: dict[int, int] = defaultdict(int)
    if recent:
        for pid, n in db.execute(
            select(PostGameVote.target_player_id, func.count()).join(PostGameSurvey, PostGameSurvey.id == PostGameVote.survey_id)
            .where(PostGameSurvey.event_id.in_(recent), PostGameVote.vote_type == VoteType.BEST_PERFORMER)
            .group_by(PostGameVote.target_player_id)
        ).all():
            counts[pid] = n
    for prof in db.scalars(select(PlayerProfile).join(Player, Player.id == PlayerProfile.player_id).where(Player.team_id == team_id)).all():
        prof.peer_vote_score = Decimal(counts.get(prof.player_id, 0))


# ---------------------------------------------------------------------------
# F11: 나와 잘 맞는 참여자 (투표 데이터만)
# ---------------------------------------------------------------------------


def compatible(db: Session, player: Player) -> list[CompatiblePlayer]:
    """상호 지목 / 나를 뽑아준 횟수 / 내가 뽑은 횟수 / 함께 뛴 쿼터. 성과 지표는 넣지 않는다 (9.4절 F11)."""
    team_events = [e.id for e in db.scalars(select(Event).where(Event.team_id == player.team_id)).all()]
    if not team_events:
        return []
    rows = db.execute(
        select(PostGameSurvey.respondent_player_id, PostGameVote.target_player_id, PostGameVote.vote_type)
        .join(PostGameVote, PostGameVote.survey_id == PostGameSurvey.id)
        .where(PostGameSurvey.event_id.in_(team_events))
    ).all()
    play_again_from_me, play_again_to_me = set(), set()
    best_from_me: dict[int, int] = defaultdict(int)
    best_to_me: dict[int, int] = defaultdict(int)
    for frm, to, vt in rows:
        if vt == VoteType.PLAY_AGAIN:
            if frm == player.id:
                play_again_from_me.add(to)
            if to == player.id:
                play_again_to_me.add(frm)
        else:
            if frm == player.id:
                best_from_me[to] += 1
            if to == player.id:
                best_to_me[frm] += 1
    others = play_again_from_me | play_again_to_me | set(best_from_me) | set(best_to_me)
    if not others:
        return []
    # 같은 팀(사이드)으로 함께 출전한 쿼터 수
    my_q = db.execute(select(QuarterLineup.quarter_id, QuarterLineup.side).where(QuarterLineup.player_id == player.id)).all()
    my_sides = dict(my_q)
    together: dict[int, int] = defaultdict(int)
    if my_sides:
        for pid, qid, side in db.execute(
            select(QuarterLineup.player_id, QuarterLineup.quarter_id, QuarterLineup.side)
            .where(QuarterLineup.quarter_id.in_(list(my_sides)), QuarterLineup.player_id.in_(others))
        ).all():
            if my_sides.get(qid) == side:
                together[pid] += 1
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(others)).options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))).all()}
    out = [
        CompatiblePlayer(
            player=to_card(players[pid]), mutual_play_again=pid in play_again_from_me and pid in play_again_to_me,
            voted_me_best=best_to_me.get(pid, 0), i_voted_best=best_from_me.get(pid, 0), together_quarters=together.get(pid, 0),
        )
        for pid in others if pid in players
    ]
    out.sort(key=lambda c: (not c.mutual_play_again, -(c.voted_me_best + c.i_voted_best), -c.together_quarters, c.player.display_name))
    return out


# ---------------------------------------------------------------------------
# 선수 통계 (F11 · S-17 기록 · 매니저 실력 지표 화면)
# ---------------------------------------------------------------------------


def player_stats(db: Session, player: Player, *, detailed: bool) -> PlayerStats:
    """참여 이력·쿼터 기록·마진 추이. `detailed`(매니저/ADMIN)면 실력 수치·사전값·정렬 순위·투표 수·변동 이력까지.

    플레이어 본인에게는 수치를 주지 않는다 (FR-28 · 9.2절 표시 정책). 마진은 원시 코트 마진의 시간 정규화 값이라
    "실력"이 아니라 "그 쿼터의 결과"다 — 화면에서도 그렇게만 설명한다.
    """
    from app.models import ManagerRanking, ManagerRankingEntry, Quarter, SkillRatingHistory
    from app.models.enums import Side
    from app.schemas.peer import MarginPoint, QuarterRecord, RankInfo, RatingChange
    from app.services.player_service import skill_grade_of, to_card

    prof = player.profile
    # 병합된 게스트 행까지 포함 (기록은 회원 쪽으로 합산)
    ids = [player.id] + [pid for (pid,) in db.execute(select(Player.id).where(Player.merged_into_player_id == player.id)).all()]

    rows = db.execute(
        select(QuarterLineup, Quarter, Event)
        .join(Quarter, Quarter.id == QuarterLineup.quarter_id)
        .join(Event, Event.id == Quarter.event_id)
        .where(QuarterLineup.player_id.in_(ids), Event.status != EventStatus.CANCELED)
        .order_by(Event.event_date.desc(), Quarter.quarter_no.desc())
    ).all()
    records: list[QuarterRecord] = []
    by_event: dict[int, list[QuarterLineup]] = defaultdict(list)
    ev_meta: dict[int, Event] = {}
    positions: dict[str, int] = defaultdict(int)
    for lu, q, ev in rows:
        by_event[ev.id].append(lu)
        ev_meta[ev.id] = ev
        if lu.position:
            positions[str(lu.position)] += 1
        my = q.black_score if lu.side == Side.BLACK else q.white_score
        their = q.white_score if lu.side == Side.BLACK else q.black_score
        records.append(
            QuarterRecord(
                event_id=ev.id, event_date=ev.event_date.isoformat(), quarter_no=q.quarter_no, side=str(lu.side),
                my_score=my, their_score=their, black_score=q.black_score, white_score=q.white_score,
                raw_margin=lu.raw_margin, normalized_margin=lu.normalized_margin, position=str(lu.position) if lu.position else None,
            )
        )
    trend = []
    for eid, lus in sorted(by_event.items(), key=lambda kv: (ev_meta[kv[0]].event_date, kv[0])):
        ms = [float(l.normalized_margin) for l in lus]
        trend.append(
            MarginPoint(
                event_id=eid, event_date=ev_meta[eid].event_date.isoformat(), title=ev_meta[eid].title, quarters=len(lus),
                avg_normalized_margin=Decimal(str(round(sum(ms) / len(ms), 2))), wins=sum(1 for l in lus if l.raw_margin > 0),
                losses=sum(1 for l in lus if l.raw_margin < 0),
            )
        )
    attended = db.scalar(
        select(func.count()).select_from(EventAttendance).join(Event, Event.id == EventAttendance.event_id)
        .where(EventAttendance.player_id.in_(ids), EventAttendance.status == AttendanceStatus.ATTEND, Event.status != EventStatus.CANCELED,
               Event.event_date <= datetime.now(ZoneInfo(get_settings().timezone)).date())
    ) or 0
    stats = PlayerStats(
        player=to_card(player, include_grade=detailed), events_attended=attended, quarters_played=len(records),
        position_distribution=dict(positions), margin_trend=trend, recent_quarters=records[:200],
    )
    if not detailed:
        return stats

    skill = prof.skill_overall if prof and prof.skill_overall is not None else (prof.prior_overall if prof else None)
    stats.skill_overall = prof.skill_overall if prof else None
    stats.prior_overall = prof.prior_overall if prof else None
    stats.prior_source = str(prof.prior_source) if prof and prof.prior_source else None
    stats.skill_confidence = prof.skill_confidence if prof else None
    stats.cumulative_residual = prof.cumulative_residual if prof else None
    stats.skill_grade = skill_grade_of(skill)
    if prof:
        stats.skill_axes = {
            "shooting": prof.skill_shooting, "ball_handling": prof.skill_ball_handling, "passing": prof.skill_passing,
            "defense": prof.skill_defense, "rebound_post": prof.skill_rebound_post, "stamina": prof.skill_stamina,
        }
    active = db.scalar(select(ManagerRanking).where(ManagerRanking.team_id == player.team_id, ManagerRanking.is_active.is_(True)))
    if active:
        entries = db.scalars(select(ManagerRankingEntry).where(ManagerRankingEntry.ranking_id == active.id)).all()
        mine = next((e for e in entries if e.player_id == player.id), None)
        if mine:
            stats.manager_rank = RankInfo(rank_no=mine.rank_no, total=len(entries), ranked_at=active.created_at)
    stats.play_again_received = db.scalar(
        select(func.count()).select_from(PostGameVote).where(PostGameVote.target_player_id.in_(ids), PostGameVote.vote_type == VoteType.PLAY_AGAIN)
    ) or 0
    stats.play_again_mutual = db.scalar(
        select(func.count()).select_from(ChemistryScore)
        .where(((ChemistryScore.player_a_id == player.id) | (ChemistryScore.player_b_id == player.id)), ChemistryScore.pref_mutual.is_(True))
    ) or 0
    hist = db.scalars(
        select(SkillRatingHistory).where(SkillRatingHistory.player_id.in_(ids)).order_by(SkillRatingHistory.created_at.desc(), SkillRatingHistory.id.desc()).limit(200)
    ).all()
    stats.history = [
        RatingChange(source=str(h.source), before_value=h.before_value, after_value=h.after_value, delta=h.delta, reason=h.reason, created_at=h.created_at)
        for h in hist
    ]
    return stats


def leaderboard(db: Session, team_id: int, *, metric: str, period: str | None, include_grade: bool) -> list:
    """팀 리더보드. metric: attendance(참여율) / quarters(출전 쿼터) / residual(잔차 누적, 매니저)."""
    from datetime import date as _date

    from app.models import Quarter
    from app.schemas.peer import LeaderboardEntry

    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    lo, hi = None, None
    if period:
        try:
            if "-Q" in period:
                y, q = period.split("-Q")
                lo = _date(int(y), (int(q) - 1) * 3 + 1, 1)
                hi = _date(int(y) + (int(q) == 4), 1 if int(q) == 4 else int(q) * 3 + 1, 1)
            elif len(period) == 7 and period[4] == "-":
                y, m = period.split("-")
                lo = _date(int(y), int(m), 1)
                hi = _date(int(y) + (int(m) == 12), 1 if int(m) == 12 else int(m) + 1, 1)
            else:
                raise ValueError(period)
        except ValueError:
            raise errors.ValidationError("period 는 2026-Q3 또는 2026-09 형식이에요.") from None
    ev_stmt = select(Event).where(Event.team_id == team_id, Event.status != EventStatus.CANCELED, Event.event_date <= today)
    if lo:
        ev_stmt = ev_stmt.where(Event.event_date >= lo, Event.event_date < hi)
    event_ids = list(db.scalars(select(ev_stmt.subquery().c.id)).all())
    players = db.scalars(
        select(Player).where(Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE, Player.merged_into_player_id.is_(None))
        .options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))
    ).all()
    attended: dict[int, int] = defaultdict(int)
    eligible: dict[int, int] = defaultdict(int)  # 응답 행이 있는 회차 수 = 가입 이후 회차 (행은 일정 생성 시 활성 회원에게만 만들어진다)
    quarters: dict[int, int] = defaultdict(int)
    if event_ids:
        for pid, st, n in db.execute(
            select(EventAttendance.player_id, EventAttendance.status, func.count()).where(EventAttendance.event_id.in_(event_ids)).group_by(EventAttendance.player_id, EventAttendance.status)
        ).all():
            eligible[pid] += n
            if st == AttendanceStatus.ATTEND:
                attended[pid] = n
        for pid, n in db.execute(
            select(QuarterLineup.player_id, func.count()).join(Quarter, Quarter.id == QuarterLineup.quarter_id).where(Quarter.event_id.in_(event_ids)).group_by(QuarterLineup.player_id)
        ).all():
            quarters[pid] = n
    out = []
    for p in players:
        if metric == "attendance":
            n_el = eligible[p.id]
            value = Decimal(str(round(attended[p.id] / n_el, 2))) if n_el else Decimal(0)
            detail = f"{attended[p.id]}/{n_el}회"
        elif metric == "quarters":
            value, detail = Decimal(quarters[p.id]), f"{quarters[p.id]}쿼터"
        else:
            value = p.profile.cumulative_residual if p.profile and p.profile.cumulative_residual is not None else Decimal(0)
            detail = f"평가 쿼터 {quarters[p.id]}개"
        out.append(LeaderboardEntry(player=to_card(p, include_grade=include_grade), value=value, detail=detail))
    out.sort(key=lambda e: (-float(e.value), e.player.display_name))
    for i, e in enumerate(out):
        e.rank = i + 1
    return out
